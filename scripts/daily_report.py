"""Milestone 6 stage 2: the Claude Routine fallback (references/cloud.md section 8).

If Claude Routines aren't available on the class plan, a scheduled GitHub Actions job
(.github/workflows/daily_report.yml) runs this instead: reads exports/daily_summary.json
(written every minute by agent/cloud_loop.py) and docs/ai-use-policy.md, asks Sonnet to write
a plain-English status report, and writes reports/<date>.md.

Usage:
  uv run python scripts/daily_report.py --state state/ --out reports/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import ROOT, load_agent_config  # noqa: E402

SYSTEM = ("You write a short daily status report for the maintainers of a governed data "
         "pipeline. Use only the numbers and facts in the summary given; never invent or "
         "estimate a figure that isn't there. Plain English, short headings, under 400 words.")


def build_prompt(summary: dict, policy_text: str) -> str:
    lines = ["Today's pipeline summary (JSON):", "```json", json.dumps(summary, indent=2, default=str), "```"]
    if policy_text:
        lines += ["", "The AI use policy, for reference:", policy_text]
    lines += ["", "Write the daily report: imports processed, held imports and why, open "
                  "incidents, model usage and cost by expert, the latest published batch, and "
                  "anything in ai_use_policy_flags (call it out explicitly if non-empty)."]
    return "\n".join(lines)


def write_report(client, summary: dict, policy_text: str, out_dir: Path, model: str,
                 today: date | None = None) -> Path:
    today = today or date.today()
    resp = client.messages.create(model=model, max_tokens=1000, system=SYSTEM,
                                  messages=[{"role": "user", "content": build_prompt(summary, policy_text)}])
    text = resp.content[0].text
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today.isoformat()}.md"
    path.write_text(text, encoding="utf-8")
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", type=Path, required=True, help="the checked-out data branch")
    p.add_argument("--out", type=Path, default=ROOT / "reports")
    args = p.parse_args()

    summary_path = args.state / "exports" / "daily_summary.json"
    if not summary_path.exists():
        raise SystemExit(f"{summary_path} not found -- has the pipeline run at least once?")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    policy_path = ROOT / "docs" / "ai-use-policy.md"
    policy_text = policy_path.read_text(encoding="utf-8") if policy_path.exists() else ""

    import anthropic
    client = anthropic.Anthropic()
    cfg = load_agent_config()
    path = write_report(client, summary, policy_text, args.out, cfg["models"]["sonnet"])
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
