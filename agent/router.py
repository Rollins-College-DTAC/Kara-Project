"""Mixture-of-experts router (application level).

This is not the MoE architecture inside a neural network, where a learned gate sends tokens
to sub-networks. Here a plain, readable function sends each TASK to the expert model best
suited to it, and every choice is logged with its reason in model_usage_log.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    expert: str   # jev, haiku, sonnet or rules
    reason: str   # written to model_usage_log.route_reason


def route(task: str, record: dict, context: dict) -> Route:
    """Pick an expert for one task.

    record:  {"text": the redacted note}
    context: {"enabled", "budget_ok", "jev_available", "claude_available", "escalate"}
    """
    # Rule 1: kill switch.
    if not context.get("enabled", True):
        return Route("rules", "kill switch on: rules only")
    # Rule 6: budget cap.
    if not context.get("budget_ok", True):
        return Route("rules", "token budget reached: rules only")
    if task in ("classify", "extract") and not record.get("text"):
        return Route("rules", "no free text: nothing for a model to read")

    claude_ok = context.get("claude_available", True)
    # Rule 2: classification is multiple choice, which is Jev's job.
    if task == "classify":
        if context.get("jev_available"):
            return Route("jev", "multiple-choice questions: Jev (fast, returns probabilities)")
        if claude_ok:
            return Route("haiku", "Jev unavailable: Haiku answers the same questions with a JSON schema")
        return Route("rules", "Jev and Claude unavailable: rules")
    # Rules 3 and 4: extraction writes values, which Jev cannot do; escalate hard records.
    if task == "extract":
        if not claude_ok:
            return Route("rules", "Claude unavailable (no API key): rules")
        if context.get("escalate"):
            return Route("sonnet", f"escalated: {context['escalate']}")
        return Route("haiku", "extract values from free text: Haiku (Jev only chooses among options)")
    # Rule 5: explanations of held imports are rare and need good writing.
    if task == "explain":
        return Route("sonnet", "explain a held import in plain English: Sonnet") if claude_ok \
            else Route("rules", "Claude unavailable: template explanation")
    raise ValueError(f"unknown task: {task}")
