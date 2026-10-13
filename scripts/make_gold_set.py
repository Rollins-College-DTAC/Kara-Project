"""Draft the 50-record gold set with BLANK label columns, for Kara to label by hand.

Labels are filled in by a person before any model is run on these records.
The script refuses to overwrite a file that already has labels (use --force only on purpose).

Usage: python scripts/make_gold_set.py [--out gold_set.csv] [--seed 2026]
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.evaluation import GOLD_COLUMNS, LABEL_COLUMNS  # noqa: E402
from generator import generate as g  # noqa: E402

MIX = {"injection": len(g.INJECTION_NOTES), "empty": 3, "hard": 22}  # the rest are ordinary notes
TOTAL = 50


def build_candidates(seed: int = 2026) -> list[str]:
    r = random.Random(seed)
    notes: list[str] = list(g.INJECTION_NOTES)  # every injection style, including the subtle ones
    notes += ["", "N/A", "n/a"][: MIX["empty"]]
    seen = set(notes)

    def add(hard: bool, count: int) -> None:
        added, tries = 0, 0
        while added < count and tries < 10_000:
            tries += 1
            text = g.make_note(r, r.choice([2022, 2023, 2024, 2025]), 0.6, False, hard)
            if text not in seen:
                seen.add(text)
                notes.append(text)
                added += 1

    add(True, MIX["hard"])
    add(False, TOTAL - len(notes))
    r.shuffle(notes)
    return notes


def has_labels(path: Path) -> bool:
    with open(path, newline="", encoding="utf-8") as f:
        return any(any((row.get(c) or "").strip() for c in LABEL_COLUMNS) for row in csv.DictReader(f))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="gold_set.csv")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--force", action="store_true", help="overwrite even if labels exist (destroys your labels)")
    args = p.parse_args()
    out = Path(args.out)
    if out.exists() and has_labels(out) and not args.force:
        raise SystemExit(f"{out} already has labels. Not overwriting. (Use --force only if you mean it.)")
    notes = build_candidates(args.seed)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=GOLD_COLUMNS)
        w.writeheader()
        for i, text in enumerate(notes, start=1):
            w.writerow({"gold_id": f"G{i:02d}", "notes": text})
    print(f"Wrote {len(notes)} unlabeled records to {out}. Label them by hand (see docs/gold_set_labeling_guide.md).")


if __name__ == "__main__":
    main()
