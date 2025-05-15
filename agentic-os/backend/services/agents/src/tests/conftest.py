# tests/conftest.py

import time
import pytest
import requests
from pprint import pformat

from shared.client_agents import (
    health,
    ready,
    list_registry,
    delete_agent_role,
)
from shared.client_repos import ReposClient

TEST_REPO_URL = "test_agents_running_repo"
REAL_REPO_URL = "https://github.com/githubtraining/hellogitworld.git"


@pytest.fixture(scope="session", autouse=True)
def ensure_repo_exists_and_services_ready():
    """
    1) Ensure TEST_REPO_URL exists in the Repos service (delete if present, then admit)
    2) Wait for the Agents service to be healthy and ready.
    """
    repos = ReposClient()

    # 1a) Delete repo if it exists
    try:
        existing = [r["repo_url"] for r in repos.list_repos()]
    except Exception as e:
        pytest.skip(f"Could not list repos: {e!r}")

    if TEST_REPO_URL in existing:
        print(f"TEST DEBUG - Deleting pre-existing repo: {TEST_REPO_URL}")
        try:
            repos.delete_repo(TEST_REPO_URL, remove_db=True)
        except Exception as e:
            print(f"TEST DEBUG - Warning: delete_repo failed: {e!r}")

    # 1b) Admit the repo URL
    try:
        out = repos.admit_repo(
            repo_url=TEST_REPO_URL,
            team_id="testteam",
            priority=99,
        )
        print(f"TEST DEBUG - Admitted test repo:\n{pformat(out)}")
    except Exception as e:
        print(f"TEST DEBUG - Warning: admit_repo returned error (continuing): {e!r}")

    # 2a) Wait for health()
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            h = health()
            print(f"TEST DEBUG - health() -> {pformat(h)}")
            if h.get("status") == "ok":
                break
        except Exception as exc:
            print(f"TEST DEBUG - health() failed: {exc!r}")
        time.sleep(0.5)
    else:
        pytest.exit("Agents service never became healthy", returncode=1)

    # 2b) Wait for ready()
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            r = ready()
            print(f"TEST DEBUG - ready() -> {pformat(r)}")
            if r.get("ready"):
                return
        except Exception as exc:
            print(f"TEST DEBUG - ready() failed: {exc!r}")
        time.sleep(0.5)

    pytest.exit("Agents service never became ready", returncode=1)


@pytest.fixture(scope="function")
def test_repo():
    """
    Provide the repo name for tests. It will be empty of agents at test start.
    """
    yield TEST_REPO_URL


@pytest.fixture(scope="session", autouse=True)
def registry_snapshot_and_cleanup():
    """
    Snapshot the registry at session start, then after all tests delete
    any roles that were added during the session.
    """
    before = {r["agent_role"] for r in list_registry()}
    yield
    after = {r["agent_role"] for r in list_registry()}
    for new_role in after - before:
        try:
            delete_agent_role(new_role)
            print(f"[CLEANUP] deleted registry role {new_role!r}")
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                print(f"[CLEANUP] unexpected error deleting role {new_role!r}: {e!r}")


@pytest.fixture(scope="session", autouse=True)
def cleanup_cloned_repo():
    """
    After all tests have run, delete the test repo (and its on-disk clone)
    via the Repos service with remove_db=True.
    """
    yield
    try:
        repos = ReposClient()
        repos.delete_repo(TEST_REPO_URL, remove_db=True)
        print(f"[CLEANUP] deleted repo '{TEST_REPO_URL}' (and its clone) from Repos service")
    except Exception as e:
        print(f"[CLEANUP] warning: failed to delete repo '{TEST_REPO_URL}': {e!r}")
