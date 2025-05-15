# tests/test_delete.py

from conftest import REPO_URL

def test_delete_repo_with_db(client):
    # First, raw-add a repo so we control its repo_name in the DB
    client.add_repo(
        repo_url=REPO_URL,
        repo_name="deleter",
        repo_owner="dave",
        team_id="teamD",
        priority=5,
        metadata={},
    )

    # Now delete both filesystem clone and DB record
    resp = client.delete_repo(REPO_URL, remove_db=True)
    assert "Database record removed" in resp["message"]

    # The DB entry should be gone
    names = [r["repo_name"] for r in client.list_repos()]
    assert "deleter" not in names

def test_delete_repo_filesystem_only(client):
    # Add again under a different repo_name
    client.add_repo(
        repo_url=REPO_URL,
        repo_name="onlyfs",
        repo_owner="dave",
        team_id="teamD",
        priority=5,
        metadata={},
    )

    # Delete only the filesystem clone, keep the DB record
    resp = client.delete_repo(REPO_URL, remove_db=False)
    assert "Filesystem removal" in resp["message"]

    # The DB entry should still exist
    names = [r["repo_name"] for r in client.list_repos()]
    assert "onlyfs" in names
