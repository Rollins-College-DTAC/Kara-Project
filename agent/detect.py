"""Step 1, Detect: hash the file and skip any content we have already seen."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from agent.sql import RunContext, now_iso, run_sql


@dataclass
class Detected:
    sha256: str
    size_bytes: int
    duplicate_of: str | None  # file name of the first file with this exact content, if any


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk_size):
            h.update(block)
    return h.hexdigest()


def detect(ctx: RunContext, path: Path) -> Detected:
    """Hash the file. A hash already in file_registry means a renamed copy, so it is skipped."""
    sha = sha256_file(path)
    ctx.file_sha256 = sha
    size = path.stat().st_size

    row = run_sql(ctx, "detect",
                  "SELECT file_name FROM file_registry WHERE sha256 = ?", (sha,)).fetchone()
    if row:
        return Detected(sha, size, duplicate_of=row["file_name"])

    run_sql(ctx, "detect",
            "INSERT INTO file_registry (sha256, file_name, size_bytes, first_seen_at, run_id, status) "
            "VALUES (?, ?, ?, ?, ?, 'detected')",
            (sha, path.name, size, now_iso(), ctx.run_id))
    return Detected(sha, size, duplicate_of=None)
