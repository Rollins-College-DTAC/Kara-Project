"""Resolves which database file a dashboard page should read, and how a reviewer's decision
should be applied: the local file and a direct write (dev), or a cached GitHub fetch and a
workflow_dispatch call (cloud -- references/cloud.md). Cloud mode activates automatically
when the matching Streamlit secrets are set; otherwise every page behaves exactly as it did
before this module existed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from dashboard.db import sqlite_path
from dashboard.remote import cloud_data_configured, cloud_review_configured, fetch_db_bytes, write_to_temp


def _secrets() -> dict:
    try:
        return dict(st.secrets)
    except (AttributeError, FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return {}


@st.cache_data(ttl=30)
def _cloud_db_path(owner: str, repo: str, token: str) -> str:
    data = fetch_db_bytes(owner, repo, token)
    dest = write_to_temp(data, Path(tempfile.gettempdir()) / "lsoa_cloud_analytics.sqlite")
    return str(dest)


def resolve_db_path() -> Path:
    secrets = _secrets()
    if cloud_data_configured(secrets):
        return Path(_cloud_db_path(secrets["GH_REPO_OWNER"], secrets["GH_REPO_NAME"], secrets["GH_DATA_TOKEN"]))
    return sqlite_path()


def reviewer_passcode() -> str | None:
    return _secrets().get("REVIEWER_PASSCODE")


def cloud_review_secrets() -> dict | None:
    secrets = _secrets()
    if not cloud_review_configured(secrets):
        return None
    return {"owner": secrets["GH_REPO_OWNER"], "repo": secrets["GH_REPO_NAME"], "token": secrets["GH_REVIEW_TOKEN"]}
