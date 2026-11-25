"""Turn the ABA Employment Summary spreadsheets in data_real/ into pipeline imports.

Writes one JSON import per graduating class into the agent's inbox, oldest first, so the normal
pipeline (Detect, Land, Load, Decide) processes them like any other import. Re-running is safe:
an unchanged file has the same hash and is skipped as a duplicate.

Usage:
  uv run python scripts/import_aba.py                 # data_real/ -> inbox/
  uv run python scripts/import_aba.py --src data_real --out inbox
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.aba import load_employment_file  # noqa: E402
from agent.config import ROOT, load_agent_config  # noqa: E402


def convert(src: Path, out: Path) -> list[Path]:
    by_year: dict[int, tuple[Path, list[dict]]] = {}
    for path in sorted(src.glob("Employment_Summary_*.xlsx")):
        year, records = load_employment_file(path)
        by_year[year] = (path, records)  # a duplicate download of the same year just overwrites

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for year in sorted(by_year):
        records = by_year[year][1]
        target = out / f"aba_employment_{year}.json"
        target.write_text(json.dumps(records, indent=1), encoding="utf-8")
        written.append(target)
        time.sleep(0.05)  # distinct modified times keep the oldest class first
    return written


def main() -> None:
    cfg = load_agent_config()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", type=Path, default=ROOT / "data_real")
    p.add_argument("--out", type=Path, default=cfg["inbox"])
    args = p.parse_args()
    files = convert(args.src, args.out)
    if not files:
        raise SystemExit(f"no Employment_Summary_*.xlsx files found in {args.src}")
    for f in files:
        print(f"wrote {f}")


if __name__ == "__main__":
    main()
