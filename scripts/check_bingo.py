#!/usr/bin/env python3
"""Check a README's Portfolio BINGO card against the project minimums.

Usage: python scripts/check_bingo.py README.md
Exit code 0 when the minimums are met, 1 otherwise.
"""
import re
import sys
from pathlib import Path

REQUIRED_TOTAL = 16      # number of required squares on the card
MIN_NUMBERS = 2          # minimum checked squares in the N column
MIN_CHECKED = 18         # minimum checked squares, excluding the free center
NUMBERS_COLUMN = 2       # zero-based index of the N column

CELL = re.compile(r"\[(?P<mark>[ xX])\]\s*(?P<star>★)?\s*(?P<free>FREE:)?\s*\[(?P<label>[^\]]+)\]\((?P<link>[^)]*)\)")


def parse_card(text):
    """Return the 5x5 grid of parsed cells from the first BINGO table."""
    start = text.find("Portfolio BINGO")
    if start == -1:
        sys.exit("No 'Portfolio BINGO' section found.")
    rows = []
    for line in text[start:].splitlines():
        if not line.strip().startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue  # separator row
        parsed = [CELL.search(c) for c in cells]
        if not any(parsed):
            continue  # header row
        rows.append(parsed)
    if len(rows) != 5 or any(len(r) != 5 for r in rows):
        sys.exit(f"Expected a 5x5 card, found {len(rows)} rows.")
    return rows


def is_real_link(link):
    link = link.strip()
    return bool(link) and link.lower() not in {"link", "#", "todo", "tbd"}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    grid = parse_card(Path(sys.argv[1]).read_text(encoding="utf-8"))

    done = [[False] * 5 for _ in range(5)]
    missing_required, no_link, required_count = [], [], 0
    checked_total, numbers_checked = 0, 0

    for r, row in enumerate(grid):
        for c, m in enumerate(row):
            if m is None:
                sys.exit(f"Could not read square at row {r + 1}, column {c + 1}.")
            label = m["label"]
            if m["free"]:
                done[r][c] = True
                continue
            ticked = m["mark"] in "xX"
            linked = is_real_link(m["link"])
            if ticked and not linked:
                no_link.append(label)
            counts = ticked and linked
            done[r][c] = counts
            if m["star"]:
                required_count += 1
                if not counts:
                    missing_required.append(label)
            if counts:
                checked_total += 1
                if c == NUMBERS_COLUMN:
                    numbers_checked += 1

    lines = []
    for i in range(5):
        if all(done[i]):
            lines.append(f"row {i + 1}")
        if all(done[r][i] for r in range(5)):
            lines.append(f"column {'BINGO'[i]}")
    if all(done[i][i] for i in range(5)):
        lines.append("diagonal")
    if all(done[i][4 - i] for i in range(5)):
        lines.append("anti-diagonal")

    print(f"Required squares done: {required_count - len(missing_required)}/{required_count}")
    print(f"N column (statistics) done: {numbers_checked} (minimum {MIN_NUMBERS})")
    print(f"Total squares done: {checked_total}/24 (minimum {MIN_CHECKED})")
    if required_count != REQUIRED_TOTAL:
        print(f"Warning: card has {required_count} required squares; expected {REQUIRED_TOTAL}.")
    for label in missing_required:
        print(f"  Missing required: {label}")
    for label in no_link:
        print(f"  Ticked but no real link: {label}")
    if lines:
        print("BINGO lines: " + ", ".join(lines))

    passed = (not missing_required and numbers_checked >= MIN_NUMBERS
              and checked_total >= MIN_CHECKED)
    print("RESULT: minimums met" if passed else "RESULT: not yet")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
