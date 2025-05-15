# tests/test_claim.py

import pytest
import time
import threading

from shared.client_repos import ReposClientError
from conftest import REPO_URL

def test_claim_repo_and_check_status(client):
    # Admit via URL; extract the repo_name chosen
    resp = client.admit_repo(repo_url=REPO_URL, team_id="teamA", priority=5)
    repo_name = resp["repo_name"]

    # Claim it
    claim = client.claim_repo(ttl=120)
    assert claim["repo_name"] == repo_name
    assert claim["status"] == "claimed"

def test_claim_when_empty(client):
    # First exhaust any existing unclaimed repos
    while True:
        try:
            client.claim_repo()
        except ReposClientError:
            break

    # Now there should be none left: expect 404 Not Found
    with pytest.raises(ReposClientError) as excinfo:
        client.claim_repo()

    err = excinfo.value
    assert err.response.status_code == 404
    body = err.response.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)

def test_priority_ordering(client):
    # Directly insert two repos at different priorities (skipping the git clone)
    high = client.add_repo(
        repo_url="high",
        repo_name="high",
        repo_owner="userX",
        team_id="teamX",
        priority=100,
        metadata={},
        jdk_version=None,
    )["repo_name"]
    low = client.add_repo(
        repo_url="low",
        repo_name="low",
        repo_owner="userY",
        team_id="teamY",
        priority=1,
        metadata={},
        jdk_version=None,
    )["repo_name"]

    # First claim should be the high‐priority one
    first  = client.claim_repo()["repo_name"]
    second = client.claim_repo()["repo_name"]

    assert first  == high
    assert second == low

def test_claim_blocking_returns_if_repo_immediately_available(client):
    resp = client.admit_repo(repo_url=REPO_URL, team_id="bar", priority=10)
    repo_name = resp["repo_name"]

    t0 = time.time()
    claim = client.claim_repo_blocking(timeout=4.0)
    t1 = time.time()

    assert claim["repo_name"] == repo_name
    # Should return almost instantly
    assert (t1 - t0) < 2.0

def test_claim_blocking_waits_until_available(client):
    # Ensure the queue is empty first
    while True:
        try:
            client.claim_repo()
        except ReposClientError:
            break

    # Schedule an admit after ~1.2s
    def delayed_admit():
        time.sleep(1.2)
        client.admit_repo(repo_url=REPO_URL, team_id="tim", priority=5)

    thread = threading.Thread(target=delayed_admit)
    thread.start()

    t0 = time.time()
    claim = client.claim_repo_blocking(timeout=5.0)
    t1 = time.time()
    thread.join()

    assert claim["repo_name"]  # non‐empty
    assert 1.0 < (t1 - t0) < 4.1

def test_claim_blocking_times_out(client):
    # Empty the queue
    while True:
        try:
            client.claim_repo()
        except ReposClientError:
            break

    t0 = time.time()
    with pytest.raises(ReposClientError) as excinfo:
        client.claim_repo_blocking(timeout=2.0)
    t1 = time.time()

    # Should have waited roughly the timeout
    assert 1.6 < (t1 - t0) < 3.1

    # And now assert we got a 404 on timeout
    err = excinfo.value
    assert err.response.status_code == 404
    # The response is plain‐text, not JSON
    text = err.response.text or ""
    assert "No available repository to claim after" in text
