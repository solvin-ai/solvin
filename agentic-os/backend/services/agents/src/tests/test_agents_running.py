# tests/test_agents_running.py

import pytest
from pprint import pformat

from shared.client_agents import (
    list_running_agents,
    set_current_agent,
    get_current_running_agent,
    get_agent_stack,
    upsert_agent_role,
    list_registry,
)

@pytest.mark.order(5)
def test_empty_agent_stack(test_repo, test_task):
    """
    When no agents have ever been set, the stack is empty.
    """
    repo_url  = test_repo

    stack = get_agent_stack(repo_url=repo_url)
    assert isinstance(stack, list)
    assert stack == [], f"Expected empty stack, got: {pformat(stack)}"

@pytest.mark.order(6)
def test_agents_running_and_stack(test_repo, test_task):
    """
    Full flow:
     1) list_running_agents starts empty
     2) upsert + set root → agent_id '001'
     3) upsert + set second → agent_id '002'
     4) get_current_running_agent returns the right one at each step
     5) get_agent_stack returns [root, second]
    """
    repo_url  = test_repo

    # 1) Repo starts empty
    start_list = list_running_agents(repo_url)
    assert start_list == [], f"Expected empty repo, got: {pformat(start_list)}"

    # 2) Create "root" role and make it current → '001'
    root_role = "root"
    upsert_agent_role(
        role=root_role,
        description="Root agent for testing",
        tools=[],
        prompt="You are the root agent."
    )
    assert any(r["agent_role"] == root_role for r in list_registry()), "root role not in registry"

    root_resp = set_current_agent(
        agent_role=root_role,
        agent_id="001",
        repo_url=repo_url
    )
    assert root_resp["agent_id"] == "001", f"Expected '001', got {root_resp['agent_id']}"

    cur1 = get_current_running_agent(repo_url)
    assert cur1["agent_id"] == "001", f"Expected current=001, got {pformat(cur1)}"

    # 3) Register a second role and switch to it → '002'
    second_role = "test_running_agents"
    upsert_agent_role(
        role=second_role,
        description="Role for test_agents_running",
        tools=["read_file", "directory_tree"],
        prompt="You are a running agent."
    )
    assert any(r["agent_role"] == second_role for r in list_registry()), "second role missing"

    second_resp = set_current_agent(
        agent_role=second_role,
        agent_id="002",
        repo_url=repo_url
    )
    assert second_resp["agent_id"] == "002", f"Expected '002', got {second_resp['agent_id']}"

    cur2 = get_current_running_agent(repo_url)
    assert cur2["agent_id"] == "002", f"Expected current=002, got {pformat(cur2)}"

    # 4) Verify the agent stack is [root, second]
    stack = get_agent_stack(repo_url)
    assert isinstance(stack, list)
    assert len(stack) == 2, f"Expected stack of length 2, got {len(stack)}"
    assert stack[0]["agent_id"] == "001", f"Position 0 should be '001', got {pformat(stack)}"
    assert stack[1]["agent_id"] == "002", f"Position 1 should be '002', got {pformat(stack)}"
