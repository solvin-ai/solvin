# tests/test_agents_clear.py

import pytest

from shared.client_agents import (
    list_running_agents,
    add_running_agent,
    clear_repo,
)

@pytest.mark.order(4)
@pytest.mark.usefixtures("test_repo")
def test_clear_repo_endpoint(test_repo):
    repo_url = test_repo

    # 1) Create two extra agents in this repo (beyond the single auto‐seeded one).
    a1 = add_running_agent("test_role", repo_url)
    a2 = add_running_agent("root",      repo_url)

    # Verify we got back agent dicts
    assert isinstance(a1, dict) and "agent_id" in a1
    assert isinstance(a2, dict) and "agent_id" in a2

    # 2) list_running_agents returns a list of agent dicts
    before_agents = list_running_agents(repo_url)
    assert isinstance(before_agents, list), f"Expected list, got {type(before_agents)}"
    assert len(before_agents) >= 2, f"Should have at least two agents before clear, got {len(before_agents)}"

    # 3) Call clear_repo via client helper, returns the unwrapped data dict
    clear_resp = clear_repo(repo_url)
    assert isinstance(clear_resp, dict), f"Expected dict from clear_repo, got {type(clear_resp)}"
    assert "message" in clear_resp, f"Expected 'message' key in clear_repo response, got {clear_resp!r}"
    assert repo_url in clear_resp["message"], f"Response message does not mention repo: {clear_resp['message']}"

    # 4) After clear: no agents should remain
    after_agents = list_running_agents(repo_url)
    assert isinstance(after_agents, list), f"Expected list, got {type(after_agents)}"
    assert after_agents == [], f"Expected no agents after clear, got: {after_agents!r}"