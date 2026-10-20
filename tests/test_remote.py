"""Tests for dashboard/remote.py: the cloud-mode GitHub API calls.

Every call takes its HTTP function as a parameter, so these inject a fake and never touch a
real network -- no GitHub token needed to run this suite.
"""

import pytest

from dashboard.remote import (cloud_data_configured, cloud_review_configured, fetch_db_bytes,
                              trigger_review_workflow, write_to_temp)


class FakeResponse:
    def __init__(self, content=b"", status_code=200, raise_exc=None):
        self.content = content
        self.status_code = status_code
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc


def test_cloud_data_configured_requires_all_three_secrets():
    assert cloud_data_configured({"GH_DATA_TOKEN": "t", "GH_REPO_OWNER": "o", "GH_REPO_NAME": "r"})
    assert not cloud_data_configured({"GH_DATA_TOKEN": "t"})
    assert not cloud_data_configured({})


def test_cloud_review_configured_requires_all_three_secrets():
    assert cloud_review_configured({"GH_REVIEW_TOKEN": "t", "GH_REPO_OWNER": "o", "GH_REPO_NAME": "r"})
    assert not cloud_review_configured({"GH_DATA_TOKEN": "t"})  # data token isn't a review token


def test_fetch_db_bytes_calls_the_contents_api_with_the_raw_media_type_and_ref():
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        return FakeResponse(content=b"sqlite-bytes")

    data = fetch_db_bytes("kara", "lsoa", "tok123", get=fake_get)
    assert data == b"sqlite-bytes"
    url, params, headers = calls[0]
    assert url == "https://api.github.com/repos/kara/lsoa/contents/data/analytics.sqlite"
    assert params == {"ref": "data"}
    assert headers["Authorization"] == "Bearer tok123"
    assert headers["Accept"] == "application/vnd.github.raw"


def test_fetch_db_bytes_raises_on_a_bad_response():
    def fake_get(*a, **kw):
        return FakeResponse(raise_exc=RuntimeError("404"))

    with pytest.raises(RuntimeError):
        fetch_db_bytes("kara", "lsoa", "tok", get=fake_get)


def test_write_to_temp_creates_parent_dirs_and_writes_bytes(tmp_path):
    dest = tmp_path / "nested" / "db.sqlite"
    result = write_to_temp(b"hello", dest)
    assert result == dest and dest.read_bytes() == b"hello"


def test_trigger_review_workflow_posts_the_right_dispatch_payload():
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return FakeResponse(status_code=204)

    status = trigger_review_workflow("kara", "lsoa", "tok456", "inc-1", "release", "KB", post=fake_post)
    assert status == 204
    url, body, headers = calls[0]
    assert url == "https://api.github.com/repos/kara/lsoa/actions/workflows/review.yml/dispatches"
    assert body == {"ref": "main", "inputs": {"incident_id": "inc-1", "decision": "release", "reviewer": "KB"}}
    assert headers["Authorization"] == "Bearer tok456"
