"""Agent settings: read config.toml and .env, let environment variables override, resolve paths.

Keys are read from the environment only (.env locally, secrets in the cloud). They are never
stored in config, printed or logged.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env reader: KEY=value lines; existing environment variables win."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None or value == "" else value.strip().lower() in ("1", "true", "yes", "on")


def load_models_config(raw: dict) -> dict:
    m = dict(raw)
    m["enabled"] = _env_bool("MODEL_CALLS_ENABLED", m.get("enabled", True))
    for key, env in (("max_tokens_per_run", "MAX_TOKENS_PER_RUN"), ("max_tokens_per_day", "MAX_TOKENS_PER_DAY")):
        if os.environ.get(env):
            m[key] = int(os.environ[env])
    m["questions_path"] = ROOT / m["questions_file"]
    m["extract_prompt_path"] = ROOT / m["extract_prompt_file"]
    return m


def load_agent_config(path: Path | None = None) -> dict:
    load_dotenv()
    path = path or ROOT / "config.toml"
    with open(path, "rb") as f:
        full = tomllib.load(f)
    cfg = full["agent"]
    if os.environ.get("DATA_DIR"):
        cfg["data_dir"] = os.environ["DATA_DIR"]
    for key in ("inbox", "processed", "quarantine", "data_dir"):
        cfg[key] = Path(cfg[key])
    cfg["sqlite_path"] = cfg["data_dir"] / "analytics.sqlite"
    cfg["raw_path"] = cfg["data_dir"] / "raw.json"
    cfg["models"] = load_models_config(full["models"])
    cfg["evaluation"] = full.get("evaluation", {})
    return cfg
