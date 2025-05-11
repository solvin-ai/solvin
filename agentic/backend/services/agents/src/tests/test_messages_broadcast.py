# tests/test_messages_broadcast.py

import json
import pytest
import requests

from shared.client_agents import (
    clear_repo,
    remove_all_messages,
    upsert_agent_role,
    add_running_agent,
    broadcast_to_agents,
    list_messages,
    list_running_agents,
)

TEST_REPO = "test_agents_running_repo"

@pytest.fixture(autouse=True)
def reset_repo_and_messages():
    """
    Before & after each test:
      - clear all running agents in TEST_REPO
      - clear any leftover messages for roles used in broadcast tests,
        across agent IDs 001–004
    """
    clear_repo(TEST_REPO)
    for role in ("alpha", "beta", "gamma", "delta", "type1", "type2"):
        for i in range(1, 5):
            agent_id = f"{i:03}"
            try:
                remove_all_messages(role, agent_id, TEST_REPO)
            except requests.HTTPError:
                pass

    yield

    clear_repo(TEST_REPO)
    for role in ("alpha", "beta", "gamma", "delta", "type1", "type2"):
        for i in range(1, 5):
            agent_id = f"{i:03}"
            try:
                remove_all_messages(role, agent_id, TEST_REPO)
            except requests.HTTPError:
                pass


def register_role(role: str):
    """Ensure the given role exists in the registry."""
    upsert_agent_role(
        role=role,
        description=f"test role {role}",
        tools=[],
        prompt=f"default prompt for {role}"
    )


def test_broadcast_single_string_message():
    register_role("alpha")
    agent = add_running_agent("alpha", repo_url=TEST_REPO)

    res = broadcast_to_agents(
        agent_roles=["alpha"],
        messages="hello, world!",
        repo_url=TEST_REPO
    )
    assert res["success_count"] == 1
    assert res["errors"] == []

    msgs = list_messages(
        agent["agent_role"],
        agent["agent_id"],
        repo_url=TEST_REPO,
        role="user",
    )
    assert [m["content"] for m in msgs] == ["hello, world!"]


def test_broadcast_list_to_multiple_agents():
    register_role("beta")
    register_role("gamma")

    b1 = add_running_agent("beta", repo_url=TEST_REPO)
    b2 = add_running_agent("beta", repo_url=TEST_REPO)
    # this one should not receive the "beta" broadcast
    add_running_agent("gamma", repo_url=TEST_REPO)

    payload = ["one", "two", "three"]
    res = broadcast_to_agents(
        agent_roles=["beta"],
        messages=payload,
        repo_url=TEST_REPO
    )
    assert res["success_count"] == 2
    assert res["errors"] == []

    for ag in (b1, b2):
        msgs = list_messages(
            ag["agent_role"],
            ag["agent_id"],
            repo_url=TEST_REPO,
            role="user",
        )
        assert [m["content"] for m in msgs] == payload


def test_broadcast_json_string_as_single_message():
    register_role("delta")
    agent = add_running_agent("delta", repo_url=TEST_REPO)

    json_payload = json.dumps(["x", "y", "z"])
    res = broadcast_to_agents(
        agent_roles=["delta"],
        messages=json_payload,
        repo_url=TEST_REPO
    )
    assert res["success_count"] == 1
    assert res["errors"] == []

    msgs = list_messages(
        agent["agent_role"],
        agent["agent_id"],
        repo_url=TEST_REPO,
        role="user",
    )
    # the raw JSON string should be delivered as one message
    assert [m["content"] for m in msgs] == [json_payload]


def test_broadcast_to_no_matching_roles_yields_zero():
    # "no_such" was never registered or spun up
    res = broadcast_to_agents(
        agent_roles=["no_such"],
        messages=["irrelevant"],
        repo_url=TEST_REPO
    )
    assert res["success_count"] == 0
    assert res["errors"] == []


def test_empty_roles_list_broadcasts_to_all_agents():
    register_role("type1")
    register_role("type2")

    a1 = add_running_agent("type1", repo_url=TEST_REPO)
    a2 = add_running_agent("type2", repo_url=TEST_REPO)

    # sanity: confirm two agents exist
    running = list_running_agents(repo_url=TEST_REPO)
    assert {ra["agent_id"] for ra in running} == {a1["agent_id"], a2["agent_id"]}

    # broadcast with empty roles list ⇒ should go to _all_ running agents
    payload = ["broadcast to everyone"]
    res = broadcast_to_agents(
        agent_roles=[],
        messages=payload,
        repo_url=TEST_REPO
    )
    # count all running agents now
    running = list_running_agents(repo_url=TEST_REPO)
    assert res["success_count"] == len(running), f"Expected {len(running)} successes, got {res['success_count']}"
    assert res["errors"] == []

    for ag in running:
        msgs = list_messages(
            ag["agent_role"],
            ag["agent_id"],
            repo_url=TEST_REPO,
            role="user",
        )
        contents = [m["content"] for m in msgs]
        # each agent must have received at least one copy of the payload
        assert payload[0] in contents, (
            f"Expected '{payload[0]}' in messages for {ag}, got {contents}"
        )
