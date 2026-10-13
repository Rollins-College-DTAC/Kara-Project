"""Shared types for experts."""

from __future__ import annotations

from dataclasses import dataclass


class ExpertUnavailable(Exception):
    """The expert cannot be called right now (no key, not configured, service down)."""


@dataclass
class ExpertResult:
    expert: str            # router name: jev, haiku, sonnet, rules
    model: str             # the model id logged in model_usage_log
    data: dict             # the raw structured answer
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cached: bool = False
