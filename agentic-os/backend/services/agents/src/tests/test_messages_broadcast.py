# tests/test_messages_broadcast.py

"""
Test file for broadcast_to_agents using the client_agents helpers.
Each test gets its own unique repo via the `test_repo` fixture.
"""

import json
import uuid
import pytest

from shared.client_agents import (
    upsert_agent_role,
    set_current_agent,
    broadcast_to_agents,
    list_messages,
    list_running_agents,
)

def register_role(role: str):
    """Ensure the given role exists in the registry."""
    upsert_agent_role(
        role=role,
        description=f"test role {role}",
        tools=[],
        prompt=f"default prompt for {role}"
    )

@pytest.mark.order(1)
def test_broadcast_single_string_message(test_repo, test_task):
    repo_url = test_repo
    role = "alpha"
    register_role(role)

    # spin up one agent
    agent_id = str(uuid.uuid4())
    agent = set_current_agent(
        agent_role=role,
        agent_id=agent_id,
        repo_url=repo_url
    )

    # broadcast a single string → becomes one "user" message
    res = broadcast_to_agents(
        agent_roles=[role],
        messages="hello, world!",
        repo_url=repo_url,
    )
    assert res["success_count"] == 1
    assert res["errors"] == []

    msgs = list_messages(
        agent_role=agent["agent_role"],
        agent_id=agent["agent_id"],
        repo_url=repo_url,
        role="user",
    )
    assert [m["content"] for m in msgs] == ["hello, world!"]

@pytest.mark.order(2)
def test_broadcast_list_to_multiple_agents(test_repo, test_task):
    repo_url = test_repo
    role_beta = "beta"
    role_gamma = "gamma"
    register_role(role_beta)
    register_role(role_gamma)

    # spin up two beta agents and one gamma agent
    b1 = set_current_agent(role_beta, str(uuid.uuid4()), repo_url=repo_url)
    b2 = set_current_agent(role_beta, str(uuid.uuid4()), repo_url=repo_url)
    _  = set_current_agent(role_gamma, str(uuid.uuid4()), repo_url=repo_url)

    payload = ["one", "two", "three"]
    res = broadcast_to_agents(
        agent_roles=[role_beta],
        messages=payload,
        repo_url=repo_url,
    )
    assert res["success_count"] == 2
    assert res["errors"] == []

    for ag in (b1, b2):
        msgs = list_messages(
            agent_role=ag["agent_role"],
            agent_id=ag["agent_id"],
            repo_url=repo_url,
            role="user",
        )
        assert [m["content"] for m in msgs] == payload

@pytest.mark.order(3)
def test_broadcast_json_string_as_single_message(test_repo, test_task):
    repo_url = test_repo
    role = "delta"
    register_role(role)

    agent = set_current_agent(
        agent_role=role,
        agent_id=str(uuid.uuid4()),
        repo_url=repo_url,
    )

    json_payload = json.dumps(["x", "y", "z"])
    res = broadcast_to_agents(
        agent_roles=[role],
        messages=json_payload,
        repo_url=repo_url,
    )
    assert res["success_count"] == 1
    assert res["errors"] == []

    msgs = list_messages(
        agent_role=agent["agent_role"],
        agent_id=agent["agent_id"],
        repo_url=repo_url,
        role="user",
    )
    # the raw JSON string should be delivered as a single message
    assert [m["content"] for m in msgs] == [json_payload]

@pytest.mark.order(4)
def test_broadcast_to_no_matching_roles_yields_zero(test_repo, test_task):
    repo_url = test_repo
    # never registered, never spun up
    res = broadcast_to_agents(
        agent_roles=["no_such"],
        messages=["irrelevant"],
        repo_url=repo_url,
    )
    assert res["success_count"] == 0
    assert res["errors"] == []

@pytest.mark.order(5)
def test_empty_roles_list_broadcasts_to_all_agents(test_repo, test_task):
    repo_url = test_repo
    role1 = "type1"
    role2 = "type2"
    register_role(role1)
    register_role(role2)

    a1 = set_current_agent(role1, str(uuid.uuid4()), repo_url=repo_url)
    a2 = set_current_agent(role2, str(uuid.uuid4()), repo_url=repo_url)

    # sanity: only those two agents exist in this repo/task
    running = list_running_agents(repo_url=repo_url)
    ids = {r["agent_id"] for r in running}
    assert ids == {a1["agent_id"], a2["agent_id"]}

    # broadcast to empty roles ⇒ broadcast to ALL running agents
    payload = ["broadcast to everyone"]
    res = broadcast_to_agents(
        agent_roles=[],
        messages=payload,
        repo_url=repo_url,
    )
    assert res["success_count"] == len(running)
    assert res["errors"] == []

    for ag in running:
        msgs = list_messages(
            agent_role=ag["agent_role"],
            agent_id=ag["agent_id"],
            repo_url=repo_url,
            role="user",
        )
        contents = [m["content"] for m in msgs]
        assert payload[0] in contents, f"Expected '{payload[0]}' in messages for {ag}"
