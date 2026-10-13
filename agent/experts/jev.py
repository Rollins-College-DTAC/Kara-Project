"""Jev (TypeSafe AI): a discriminative model that answers multiple-choice questions with probabilities.

NOT WIRED YET. The exact request and response format must come from TypeSafe's developer
documentation, and we do not guess it. Until it is wired, available() is False and the router
sends classification to Claude Haiku with the same questions (logged as the route reason).

To wire it: implement _request() from the docs, map the response to the shape
parse_classification() expects (probabilities per option, probability_true for noul), set
WIRED = True, set jev_base_url in config.toml, and keep the key in JEV_API_KEY (.env).
"""

from __future__ import annotations

from agent.experts.base import ExpertResult, ExpertUnavailable

WIRED = False


class JevExpert:
    name = "jev"
    model = "jev"

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self._api_key = api_key  # never logged

    def available(self) -> bool:
        return WIRED and bool(self.base_url) and bool(self._api_key)

    def classify(self, text: str, questions: dict) -> ExpertResult:
        if not self.available():
            raise ExpertUnavailable("Jev is not wired yet (waiting for TypeSafe's request format)")
        return self._request(text, questions)

    def _request(self, text: str, questions: dict) -> ExpertResult:  # pragma: no cover - needs docs
        raise ExpertUnavailable("Jev request format not implemented")
