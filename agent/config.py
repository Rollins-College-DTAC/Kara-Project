"""Agent settings: read config.toml, let environment variables override, resolve paths."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_agent_config(path: Path | None = None) -> dict:
    path = path or ROOT / "config.toml"
    with open(path, "rb") as f:
        cfg = tomllib.load(f)["agent"]
    if os.environ.get("DATA_DIR"):
        cfg["data_dir"] = os.environ["DATA_DIR"]
    for key in ("inbox", "processed", "quarantine", "data_dir"):
        cfg[key] = Path(cfg[key])
    cfg["sqlite_path"] = cfg["data_dir"] / "analytics.sqlite"
    cfg["raw_path"] = cfg["data_dir"] / "raw.json"
    return cfg
