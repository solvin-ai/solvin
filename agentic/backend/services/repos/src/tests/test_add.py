# tests/test_add.py

import pytest
from shared.client_repos import ReposClientConflict

def test_add_repo(client):
    resp = client.add_repo(
        repo_url="r1",
        repo_name="r1",
        repo_owner="alice",
        team_id="teamA",
        priority=5,
        metadata={},
        jdk_version=None,
    )
    assert resp["message"] == "Repository admitted"
    # Verify it shows up in the list
    repo_names = [r["repo_name"] for r in client.list_repos()]
    assert "r1" in repo_names

def test_add_duplicate_repo(client):
    # First insert succeeds
    client.add_repo(
        repo_url="r1",
        repo_name="r1",
        repo_owner="alice",
        team_id="teamA",
        priority=5,
        metadata={},
        jdk_version=None,
    )
    # Second insert with same repo_url/repo_name should raise a 409 Conflict
    with pytest.raises(ReposClientConflict) as excinfo:
        client.add_repo(
            repo_url="r1",
            repo_name="r1",
            repo_owner="bob",
            team_id="teamB",
            priority=7,
            metadata={},
            jdk_version=None,
        )
    err = excinfo.value
    # Confirm it's indeed a 409 Conflict
    assert err.response.status_code == 409
    body = err.response.json()
    assert "detail" in body
    assert "already exists" in body["detail"].lower()

def test_add_multiple_repos(client):
    # Add r2, r3, r4
    for i in range(2, 5):
        name = f"r{i}"
        resp = client.add_repo(
            repo_url=name,
            repo_name=name,
            repo_owner="bob",
            team_id="teamB",
            priority=2 + i,
            metadata={},
            jdk_version=None,
        )
        assert resp["message"] == "Repository admitted"
        # Confirm via list_repos
        assert any(r["repo_name"] == name for r in client.list_repos())
