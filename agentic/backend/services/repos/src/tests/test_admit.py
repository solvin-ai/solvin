# tests/test_admit.py

import pytest
from shared.client_repos import ReposClientConflict
from conftest import REPO_URL

def test_admit_repo(client):
    # Admit a repo by URL
    resp = client.admit_repo(
        repo_url=REPO_URL,
        team_id="teamA",
        priority=5
    )
    # Basic smoke checks
    assert resp["message"] == "Repository admitted"
    assert "repo_name" in resp
    assert "metadata" in resp

    md = resp["metadata"]
    # metadata should include at least these keys
    assert "language" in md
    assert "build_system" in md
    assert "build_system_version" in md
    assert "jdk_version" in md
    assert "source_file_count" in md
    assert "total_loc" in md
    assert "largest_file" in md
    assert "largest_file_size" in md

    # It should show up in the repo list
    names = [r["repo_name"] for r in client.list_repos()]
    assert resp["repo_name"] in names

def test_admit_duplicate_repo(client):
    # First admit succeeds
    client.admit_repo(
        repo_url=REPO_URL,
        team_id="teamA",
        priority=1
    )
    # Second admit of same URL → should raise a 409 Conflict
    with pytest.raises(ReposClientConflict) as excinfo:
        client.admit_repo(
            repo_url=REPO_URL,
            team_id="teamA",
            priority=1
        )
    err = excinfo.value
    # Confirm it's a 409 Conflict
    assert err.response.status_code == 409
    detail = err.response.json()
    assert "detail" in detail
    assert "already admitted" in detail["detail"].lower()

def test_admit_bulk(client):
    entries = [
        {"repo_url": REPO_URL, "team_id": "teamX", "priority": 1},
        {"repo_url": "https://invalid.url/does-not-exist.git", "team_id": "teamX", "priority": 1}
    ]
    results = client.admit_bulk(entries)
    assert len(results) == 2

    # First should be ok
    assert results[0]["status"] == "ok"
    assert "detail" in results[0] and results[0]["detail"]["message"] == "Repository admitted"

    # Second should be error
    assert results[1]["status"] == "error"
    assert isinstance(results[1]["detail"], (str, dict))
