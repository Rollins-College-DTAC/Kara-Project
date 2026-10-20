"""Tests for scripts/daily_report.py: the Claude Routine fallback.

Uses a fake client (like tests/test_models.py's recorded-response pattern) -- never a real
API call, never a real key.
"""

import importlib.util
from datetime import date

import pytest

from agent.config import ROOT


@pytest.fixture
def dr():
    spec = importlib.util.spec_from_file_location("daily_report", ROOT / "scripts" / "daily_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Block:
    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class FakeClient:
    """Stands in for anthropic.Anthropic(); records the call for inspection."""

    def __init__(self, text="# Daily report\n\nAll quiet."):
        self.text = text
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return _Resp(self.text)


SUMMARY = {"imports_processed_today": 3, "held_imports": [], "incidents_open": [],
          "model_usage_by_expert_today": [], "latest_published_batch": None, "ai_use_policy_flags": []}


def test_build_prompt_includes_the_summary_json(dr):
    prompt = dr.build_prompt(SUMMARY, "")
    assert '"imports_processed_today": 3' in prompt


def test_build_prompt_includes_the_policy_text_when_given(dr):
    prompt = dr.build_prompt(SUMMARY, "Rule: a person releases every held import.")
    assert "a person releases every held import" in prompt


def test_build_prompt_omits_the_policy_section_when_not_written_yet(dr):
    prompt = dr.build_prompt(SUMMARY, "")
    assert "AI use policy" not in prompt


def test_write_report_calls_the_client_with_the_configured_model_and_writes_the_file(dr, tmp_path):
    client = FakeClient(text="# Report\n\n3 imports processed.")
    path = dr.write_report(client, SUMMARY, "", tmp_path, model="claude-sonnet-5-5", today=date(2026, 10, 20))
    assert path == tmp_path / "2026-10-20.md"
    assert path.read_text(encoding="utf-8") == "# Report\n\n3 imports processed."
    assert client.calls[0]["model"] == "claude-sonnet-5-5"
    assert client.calls[0]["system"] == dr.SYSTEM


def test_main_raises_clearly_when_the_summary_file_is_missing(dr, tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["daily_report.py", "--state", str(tmp_path), "--out", str(tmp_path / "out")])
    with pytest.raises(SystemExit, match="not found"):
        dr.main()
