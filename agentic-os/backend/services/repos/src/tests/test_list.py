# tests/test_list.py

from conftest import REPO_URL

def test_list_repos(client):
    names = [f"rr{i}" for i in range(1, 5)]
    # Use the new raw‐add endpoint to register four distinct repos
    for name in names:
        client.add_repo(
            repo_url=f"{REPO_URL}/{name}",
            repo_name=name,
            repo_owner="u",
            team_id="t",
            priority=1,
            metadata={}
        )
    repo_names = [r["repo_name"] for r in client.list_repos()]
    for name in names:
        assert name in repo_names
