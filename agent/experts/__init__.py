"""The expert models the router can choose from."""

from agent.experts.base import ExpertResult, ExpertUnavailable  # noqa: F401


def build_experts(mcfg: dict) -> dict:
    """One instance per expert, keyed by the name the router uses."""
    import os

    from agent.experts.claude import ClaudeExpert
    from agent.experts.jev import JevExpert
    from agent.experts.rules import RulesExpert

    return {
        "jev": JevExpert(mcfg.get("jev_base_url", ""), os.environ.get("JEV_API_KEY", "")),
        "haiku": ClaudeExpert("haiku", mcfg["haiku"], mcfg["max_output_tokens"]),
        "sonnet": ClaudeExpert("sonnet", mcfg["sonnet"], mcfg["max_output_tokens"]),
        "rules": RulesExpert(),
    }
