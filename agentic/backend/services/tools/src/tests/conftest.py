# tests/conftest.py

import sys
import subprocess
import os
from pathlib import Path

# 1) Add services/tools/src to PYTHONPATH so imports like `shared…`, `modules…`, and `tools…` work
tests_dir = Path(__file__).parent
src_dir   = tests_dir.parent        # …/services/tools/src
sys.path.insert(0, str(src_dir))

import pytest
from shared.config import config
from modules import tools_executor

# Import the actual tool modules so we can monkey-patch their sandboxing helpers
import tools.tool_read_file      as trf
import tools.tool_directory_tree as tdt


@pytest.fixture(autouse=True)
def stub_repo_info_and_set_repos_dir(monkeypatch, tmp_path):
    """
    For every test:
      - Point REPOS_DIR at tmp_path so the executor never complains.
      - Stub out repos_client.get_repo_info() → returns dummy owner/jdk.
    """
    config.set("REPOS_DIR", str(tmp_path))
    monkeypatch.setattr(
        tools_executor.repos_client,
        "get_repo_info",
        lambda repo: {"repo_owner": "alice", "jdk_version": "11"}
    )
    yield


@pytest.fixture
def fake_local_repo(tmp_path, monkeypatch):
    """
    Creates a real Git repo under tmp_path/Hello-World with:
      - README
      - docs/guide.md
    Then monkey-patches the sandbox helpers in both tool_read_file
    and tool_directory_tree so they operate on this local checkout.
    """
    # 1) Create the fake repo directory + files
    repo_name = "Hello-World"
    repo_dir  = tmp_path / repo_name
    repo_dir.mkdir()
    (repo_dir / "README").write_text("This is a fake README\n", encoding="utf-8")
    docs = repo_dir / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nSome docs here\n", encoding="utf-8")

    # 2) Turn it into a real Git repo & commit
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "you@example.com"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.name",  "Test User"],       cwd=str(repo_dir), check=True)
    subprocess.run(["git", "add", "-A"],    cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    # 3) Ensure the executor will look under tmp_path
    config.set("REPOS_DIR", str(tmp_path))
    monkeypatch.setattr(
        tools_executor.repos_client,
        "get_repo_info",
        lambda name: {"repo_owner": "octocat", "jdk_version": "11"}
    )

    # 4) Monkey-patch inside tool_read_file so it resolves into our fake repo
    monkeypatch.setattr(
        trf,
        "resolve_repo_path",
        lambda repo, p: str(repo_dir / p)
    )
    monkeypatch.setattr(
        trf,
        "check_path",
        lambda path, allowed_root=None: path
    )

    # 5) Monkey-patch inside tool_directory_tree so it scans our fake repo
    monkeypatch.setattr(
        tdt,
        "get_safe_repo_root",
        lambda: str(repo_dir)
    )
    monkeypatch.setattr(
        tdt,
        "resolve_safe_repo_path",
        # if absolute, return as-is; else prefix with repo_dir
        lambda p: str(p) if os.path.isabs(p)
                  else str(repo_dir / p.lstrip("./"))
    )

    return {"repo_name": repo_name, "repo_owner": "octocat"}
