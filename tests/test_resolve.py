"""Tests for dashboard/resolve.py: falls back to local behavior with no secrets configured
(the normal case for local dev and for this test environment, which has no secrets.toml)."""

from dashboard.resolve import cloud_review_secrets, reviewer_passcode, resolve_db_path
from dashboard.db import sqlite_path


def test_resolve_db_path_falls_back_to_local_with_no_secrets_file():
    assert resolve_db_path() == sqlite_path()


def test_reviewer_passcode_is_none_with_no_secrets_file():
    assert reviewer_passcode() is None


def test_cloud_review_secrets_is_none_with_no_secrets_file():
    assert cloud_review_secrets() is None
