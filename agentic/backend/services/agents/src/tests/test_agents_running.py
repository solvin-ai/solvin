# tests/test_agents_running.py

import pytest
from pprint import pformat
import requests

from shared.client_agents import (
    list_running_agents,
    add_running_agent,
    set_current_agent,
    get_current_running_agent,
    upsert_agent_role,
    list_registry,
    remove_running_agent,
)

@pytest.mark.order(6)
@pytest.mark.usefixtures("test_repo")
def test_agents_running(test_repo):
    repo_url = test_repo

    # 1) Repo starts empty
    start_list = list_running_agents(repo_url)
    assert start_list == [], f"Expected empty repo, got: {pformat(start_list)}"
    print(f"TEST DEBUG - Initial agents: {pformat(start_list)}")

    # 2) Create the "root" agent first; expect it to be '001'
    root = add_running_agent("root", repo_url)
    assert root["agent_id"] == "001", f"Expected first agent_id '001', got {root['agent_id']}"
    print(f"TEST DEBUG - Added root agent: {pformat(root)}")

    # Make root the current agent
    set_current_agent(root["agent_role"], root["agent_id"], repo_url)
    cur = get_current_running_agent(repo_url)
    assert cur["agent_id"] == root["agent_id"], f"Expected current=root, got {pformat(cur)}"
    print(f"TEST DEBUG - Current after root add: {pformat(cur)}")

    # 3) Register a new role
    role        = "test_running_agents"
    description = "Role for test_agents_running"
    tools       = ["read_file", "directory_tree"]
    prompt      = "You are a running agent."
    print("TEST DEBUG - Registering new agent role")
    upsert_agent_role(role, description, tools, prompt)

    # list_registry() is global; takes no repo_url
    registry = list_registry()
    assert any(r["agent_role"] == role for r in registry), f"Role not in registry: {pformat(registry)}"
    print(f"TEST DEBUG - Registry after upsert: {pformat(registry)}")

    # 4) Add a second agent under the new role, then switch to it
    second = add_running_agent(role, repo_url)
    assert second["agent_role"] == role, f"Expected role {role}, got {second['agent_role']}"
    print(f"TEST DEBUG - Added second agent: {pformat(second)}")

    set_current_agent(second["agent_role"], second["agent_id"], repo_url)
    cur2 = get_current_running_agent(repo_url)
    assert cur2["agent_id"] == second["agent_id"], f"Expected current=second, got {pformat(cur2)}"
    print(f"TEST DEBUG - Current after switch: {pformat(cur2)}")

    # 5) Remove the second (current) agent
    remove_running_agent(second["agent_role"], second["agent_id"], repo_url)
    print("TEST DEBUG - Removed second agent")

    # 6) After removal, current should automatically fall back to root
    fallback = get_current_running_agent(repo_url)
    print("TEST DEBUG - Fallback current after removal:", pformat(fallback))
    assert fallback["agent_id"] == root["agent_id"], (
        f"Expected fallback to root/001, got {pformat(fallback)}"
    )
