"""Every model call goes through the Gateway: cache by input hash, token budget, usage logging.

- Cache: a valid answer is stored under sha256(expert, model, task, prompt version, input text),
  so re-runs on the same text cost nothing. Invalid answers are never cached.
- Budget: per-run and per-day token caps. When reached, the router sends work to rules and a
  'budget' incident is opened (once per run).
- model_usage_log: one row per call with task, expert, route reason, tokens, latency,
  confidence, estimated cost and outcome. Written directly (it is a log table).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from agent.experts.base import ExpertResult
from agent.sql import RunContext, now_iso, open_incident, run_sql


class InvalidAnswer(Exception):
    """The expert answered, but the answer failed validation. Carries the result for logging."""

    def __init__(self, result: ExpertResult, error: Exception):
        super().__init__(str(error))
        self.result = result
        self.error = error


def short(exc: Exception, n: int = 140) -> str:
    text = f"{type(exc).__name__}: {exc}".replace("\n", " ")
    return text if len(text) <= n else text[:n] + "..."


class Gateway:
    def __init__(self, ctx: RunContext, mcfg: dict, experts: dict):
        self.ctx = ctx
        self.mcfg = mcfg
        self.experts = experts
        self.run_tokens = 0
        self._budget_incident_open = False

    # ------------------------------------------------------------ budget and routing context

    def tokens_today(self) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = run_sql(self.ctx, "route",
                      "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) AS t FROM model_usage_log "
                      "WHERE substr(called_at, 1, 10) = ?", (today,)).fetchone()
        return int(row["t"])

    def budget_ok(self) -> bool:
        if self.run_tokens >= self.mcfg["max_tokens_per_run"]:
            return False
        return self.tokens_today() < self.mcfg["max_tokens_per_day"]

    def context(self, escalate: str | None = None) -> dict:
        return {
            "enabled": self.mcfg["enabled"],
            "budget_ok": self.budget_ok() if self.mcfg["enabled"] else True,
            "jev_available": self.experts["jev"].available(),
            "claude_available": self.experts["haiku"].available(),
            "escalate": escalate,
        }

    def note_budget_reached(self) -> None:
        if not self._budget_incident_open:
            open_incident(self.ctx, "budget",
                          f"token budget reached (run {self.run_tokens} tokens; caps "
                          f"{self.mcfg['max_tokens_per_run']}/run, {self.mcfg['max_tokens_per_day']}/day); "
                          "switched to rules")
            self._budget_incident_open = True

    # ------------------------------------------------------------ calls

    def _cache_key(self, expert_name: str, task: str, version: str, text: str) -> str:
        model = getattr(self.experts[expert_name], "model", expert_name)
        return hashlib.sha256(f"{expert_name}|{model}|{task}|{version}|{text}".encode()).hexdigest()

    def call(self, step: str, task: str, expert_name: str, version: str, text: str, fn, validate):
        """Run fn(expert) unless a cached valid answer exists. Returns (result, validated answer)."""
        expert = self.experts[expert_name]
        use_cache = expert_name != "rules"
        key = self._cache_key(expert_name, task, version, text)
        if use_cache:
            row = run_sql(self.ctx, step, "SELECT response_json FROM model_cache WHERE cache_key = ?",
                          (key,)).fetchone()
            if row:
                data = json.loads(row["response_json"])
                return ExpertResult(expert_name, expert.model, data, cached=True), validate(data)

        result = fn(expert)
        self.run_tokens += result.input_tokens + result.output_tokens
        try:
            parsed = validate(result.data)
        except Exception as exc:  # Pydantic ValidationError or ValueError
            raise InvalidAnswer(result, exc) from exc
        if use_cache:
            run_sql(self.ctx, step,
                    "INSERT OR REPLACE INTO model_cache (cache_key, expert, task, prompt_version, response_json, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, expert.model, task, version, json.dumps(result.data), now_iso()))
        return result, parsed

    # ------------------------------------------------------------ logging

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price = self.mcfg.get("prices", {}).get(model)
        if not price:
            return 0.0
        return round((input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000, 6)

    def log(self, step: str, task: str, expert_name: str, reason: str, version: str, *,
            result: ExpertResult | None = None, confidence: float | None = None, outcome: str,
            pii: int = 0, row_index: int | None = None) -> None:
        model = result.model if result else getattr(self.experts[expert_name], "model", expert_name)
        cached = bool(result and result.cached)
        tin = result.input_tokens if result else 0
        tout = result.output_tokens if result else 0
        self.ctx.conn.execute(
            "INSERT INTO model_usage_log (call_id, run_id, step, task, expert, route_reason, prompt_version, "
            "input_tokens, output_tokens, latency_ms, confidence, estimated_cost_usd, pii_redacted, outcome, "
            "called_at, file_name, row_index, cached) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"call-{uuid.uuid4().hex[:10]}", self.ctx.run_id, step, task, model,
             reason + (" (cache hit)" if cached else ""), version, tin, tout,
             result.latency_ms if result else 0, confidence, self.cost(model, tin, tout),
             pii, outcome, now_iso(), self.ctx.file_name, row_index, int(cached)),
        )
        self.ctx.conn.commit()
