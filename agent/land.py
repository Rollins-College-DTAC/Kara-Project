"""Step 2, Land: store every record exactly as it arrived (the raw layer, TinyDB).

Nothing is cleaned, fixed, redacted or interpreted here. Text inside records is data:
a note that says "ignore all other schools" is stored like any other string.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from tinydb import TinyDB

from agent.sql import RunContext, now_iso


class ParseError(Exception):
    """The file cannot be read as a list of records."""


def parse_file(path: Path) -> list[dict]:
    """Read a CSV or JSON import into a list of dicts, without changing any value."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            for i, row in enumerate(rows, start=1):
                if None in row:  # more fields than header columns
                    raise ParseError(f"row {i} has more fields than the header")
            records = rows
        elif suffix == ".json":
            with open(path, encoding="utf-8") as f:
                records = json.load(f)
            if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
                raise ParseError("JSON must be a list of objects")
        else:
            raise ParseError(f"unsupported file type '{suffix}'")
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise ParseError(f"cannot parse: {exc}") from exc
    if not records:
        raise ParseError("file has no records")
    return records


def land_records(ctx: RunContext, raw_path: Path, records: list[dict]) -> int:
    """Insert the records into TinyDB, each tagged with run ID, file name, hash and row number."""
    raw_path = Path(raw_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    landed_at = now_iso()
    docs = [
        {"run_id": ctx.run_id, "file_name": ctx.file_name, "file_sha256": ctx.file_sha256,
         "row_index": i, "landed_at": landed_at, "record": rec}
        for i, rec in enumerate(records)
    ]
    with TinyDB(raw_path) as db:
        db.table("raw_records").insert_multiple(docs)
    return len(docs)


def move_unique(src: Path, dest_dir: Path) -> Path:
    """Move a file into dest_dir; if the name is taken, add a numeric suffix. Never overwrites."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    n = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}-{n}{src.suffix}"
        n += 1
    shutil.move(str(src), str(dest))
    return dest
