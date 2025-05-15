# tests/test_complete.py

import pytest
from shared.client_repos import ReposClientError
from conftest import REPO_URL

def test_complete_repo(client):
    # Admit (clone + pipeline) via URL, capture the repo_url (primary key)
    admitted = client.admit_repo(
        repo_url=REPO_URL,
        team_id="teamC",
        priority=9
    )
    repo_url = admitted["repo_url"]

    # Claim it so it becomes "claimed"
    client.claim_repo()

    # Now complete it
    resp = client.complete_repo(repo_url)
    # The success message should mention "completed"
    assert "completed" in resp.get("message", "").lower()

def test_complete_nonexistent_or_unclaimed_repo(client):
    # Completing something that doesn't exist or isn't claimed should yield a 404
    with pytest.raises(ReposClientError) as excinfo:
        client.complete_repo("notexist")
    err_resp = excinfo.value.response
    assert err_resp.status_code == 404
    data = err_resp.json()
    assert "detail" in data
    assert isinstance(data["detail"], str)
