# tests/conftest.py

import os
import sys

# -------------------------------------------------------------------
# Ensure that `services/repos/src` is on the PYTHONPATH, so that
# `import shared.client_repos` will resolve.
# -------------------------------------------------------------------
HERE = os.path.dirname(__file__)        # .../services/repos/src/tests
SRC  = os.path.abspath(os.path.join(HERE, ".."))  # .../services/repos/src
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import pytest
import time
import uuid
import shutil
from pathlib import Path

from shared.client_repos import ReposClient
from shared.config import config

REPO_URL = "https://github.com/octocat/Hello-World.git"

def unique_repo_name(base, parallel=False):
    if parallel:
        return f"{base}_{uuid.uuid4().hex[:8]}"
    return base

@pytest.fixture
def client():
    return ReposClient()

def _remove_all_repos(client):
    try:
        repos = client.list_repos()
    except Exception:
        return

    for repo in repos:
        repo_url = repo.get("repo_url")
        if not repo_url:
            continue
        # Force‐delete both DB record and any filesystem clone
        try:
            client.delete_repo(repo_url, remove_db=True)
        except Exception:
            pass

@pytest.fixture(autouse=True, scope="function")
def cleanup_repos(client):
    # Before each test: remove any leftover repos
    _remove_all_repos(client)
    yield
    # After each test: remove again
    _remove_all_repos(client)
    # Also clean up on‐disk clones
    repo_root = Path(config["REPOS_DIR"])
    if repo_root.exists():
        for entry in repo_root.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)

@pytest.fixture(scope="session", autouse=True)
def cleanup_all_repos_dir():
    yield
    # After the entire session: clean out the repos directory
    repo_root = Path(config["REPOS_DIR"])
    if repo_root.exists():
        for entry in repo_root.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
