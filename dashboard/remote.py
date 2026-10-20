"""Cloud-mode database access and review decisions (references/cloud.md).

In the cloud, the dashboard never edits the database file directly -- it fetches
analytics.sqlite from the `data` branch through the GitHub contents API (never
raw.githubusercontent.com, which caches for several minutes), and starts the `review.yml`
workflow for a human's Release/Reject decision instead of writing to the file.

Every network call takes its HTTP function (get/post) as a parameter, defaulting to httpx, so
tests can inject a fake and never touch the real network.
"""

from __future__ import annotations

from pathlib import Path

import httpx

CONTENTS_URL = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"
DISPATCH_URL = "https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"
DEFAULT_DB_PATH = "data/analytics.sqlite"


def cloud_data_configured(secrets: dict) -> bool:
    return bool(secrets.get("GH_DATA_TOKEN") and secrets.get("GH_REPO_OWNER") and secrets.get("GH_REPO_NAME"))


def cloud_review_configured(secrets: dict) -> bool:
    return bool(secrets.get("GH_REVIEW_TOKEN") and secrets.get("GH_REPO_OWNER") and secrets.get("GH_REPO_NAME"))


def fetch_db_bytes(owner: str, repo: str, token: str, path: str = DEFAULT_DB_PATH,
                   ref: str = "data", get=httpx.get) -> bytes:
    url = CONTENTS_URL.format(owner=owner, repo=repo, path=path)
    resp = get(url, params={"ref": ref},
              headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw"},
              timeout=15)
    resp.raise_for_status()
    return resp.content


def write_to_temp(data: bytes, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def trigger_review_workflow(owner: str, repo: str, token: str, incident_id: str, decision: str,
                            reviewer: str, ref: str = "main", post=httpx.post) -> int:
    """Starts review.yml's workflow_dispatch instead of writing the database directly."""
    url = DISPATCH_URL.format(owner=owner, repo=repo, workflow="review.yml")
    resp = post(url, json={"ref": ref, "inputs": {"incident_id": incident_id, "decision": decision,
                                                   "reviewer": reviewer}},
               headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
               timeout=15)
    resp.raise_for_status()
    return resp.status_code
