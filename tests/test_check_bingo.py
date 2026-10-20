"""Tests for scripts/check_bingo.py against this project's actual README.md.

Not a test of the checker's internals (it's a vendored, already-tested asset) -- a guard
against someone editing README.md's BINGO card into a shape the checker can't parse, or
silently breaking a link.
"""

import subprocess
import sys

from agent.config import ROOT


def test_check_bingo_parses_the_real_readme_without_crashing():
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_bingo.py"),
                             str(ROOT / "README.md")], capture_output=True, text=True)
    assert result.returncode in (0, 1)  # 1 = minimums not met yet, not a parse failure
    assert "Required squares done" in result.stdout


def test_every_linked_file_in_the_readme_bingo_card_actually_exists():
    import re
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    start = text.find("Portfolio BINGO")
    links = re.findall(r"\[x\][^|]*?\]\(([^)]+)\)", text[start:])
    real_links = [link for link in links if link not in ("link", "#")]
    assert real_links, "expected at least one checked square with a real link"
    for link in real_links:
        assert (ROOT / link).exists(), f"linked proof file does not exist: {link}"
