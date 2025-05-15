# tests/test_messages.py

"""
Test file for message CRUD operations and filters using the client_agents helpers.
Assumes a test_repo fixture that sets REPO_URL in config and a test_task fixture.
"""

import pytest
import uuid
from pprint import pformat

from shared.client_agents import (
    upsert_agent_role,
    delete_agent_role,
    set_current_agent,
    add_message,
    list_messages,
    get_message,
    remove_message,
)

@pytest.mark.order(7)
def test_messages_crud_and_filters(test_repo, test_task):
    repo_url = test_repo

    # 1) Register an agent role
    role = "test_messages"
    description = "Test agent for message API."
    tools = ["read_file", "directory_tree"]
    prompt = "You are a message test agent."
    reg = upsert_agent_role(role, description, tools, prompt)
    print("TEST DEBUG - Registry entry:", pformat(reg))

    # 2) "Start" a new running agent by choosing a UUID and setting it current
    agent_id = str(uuid.uuid4())
    agent = set_current_agent(
        agent_role=role,
        agent_id=agent_id,
        repo_url=repo_url,
    )
    print(f"TEST DEBUG - Running agent id: {agent['agent_id']}")

    try:
        # 3) Add several messages under different roles
        payloads = [
            ("user",      "Hello!"),
            ("assistant", "Hi there!"),
            ("user",      "What's in the directory?"),
            ("assistant", "directory_tree output ..."),
        ]
        added = []
        for msg_role, content in payloads:
            msg = add_message(
                agent_role=role,
                agent_id=agent_id,
                role=msg_role,
                content=content,
                repo_url=repo_url,
            )
            # add_message returns {"turn_id": int, "message_ids": [int, ...]}
            assert "turn_id" in msg and "message_ids" in msg
            assert isinstance(msg["turn_id"], int)
            assert isinstance(msg["message_ids"], list)
            added.append(msg)
        print("TEST DEBUG - Added messages:", pformat(added))

        # Build expected map: each message_id → (role, content)
        expected = {}
        for idx, m in enumerate(added):
            r, c = payloads[idx]
            for mid in m["message_ids"]:
                expected[mid] = (r, c)

        # 4) List all messages and verify our IDs & content & role
        all_msgs = list_messages(
            agent_role=role,
            agent_id=agent_id,
            repo_url=repo_url,
        )
        print("TEST DEBUG - All messages:", pformat(all_msgs))
        returned_ids = {m["message_id"] for m in all_msgs}
        assert set(expected).issubset(returned_ids)

        # Verify each message record
        our_msgs = [m for m in all_msgs if m["message_id"] in expected]
        assert len(our_msgs) == len(expected)
        for m in our_msgs:
            exp_role, exp_content = expected[m["message_id"]]
            assert m["role"] == exp_role
            assert m["content"] == exp_content
            # meta should include a timestamp and a top-level "turn"
            assert "timestamp" in m["meta"]
            assert isinstance(m["meta"]["timestamp"], str)
            assert "turn" in m and isinstance(m["turn"], int)

        # 5) Get individual messages by ID
        for msg_id, (exp_role, exp_content) in expected.items():
            fetched = get_message(
                agent_role=role,
                agent_id=agent_id,
                message_id=msg_id,
                repo_url=repo_url,
            )
            print(f"TEST DEBUG - get_message({msg_id}):", pformat(fetched))
            assert fetched["message_id"] == msg_id
            assert fetched["role"] == exp_role
            assert fetched["content"] == exp_content

        # 6) Test filtering by role
        for role_filter in ["user", "assistant", "tool", "system", "developer"]:
            role_msgs = list_messages(
                agent_role=role,
                agent_id=agent_id,
                role=role_filter,
                repo_url=repo_url,
            )
            print(f"TEST DEBUG - Messages for role={role_filter}:", pformat(role_msgs))
            assert all(m["role"] == role_filter for m in role_msgs)
            # If we added messages with this role, expect non-empty
            if any(r == role_filter for r, _ in payloads):
                assert role_msgs, f"Expected messages for role={role_filter}"

        # 7) Test filtering by turn
        turn_ids = {m["turn"] for m in our_msgs}
        if turn_ids:
            tid = next(iter(turn_ids))
            turn_msgs = list_messages(
                agent_role=role,
                agent_id=agent_id,
                turn_id=tid,
                repo_url=repo_url,
            )
            print(f"TEST DEBUG - Messages for turn_id={tid}:", pformat(turn_msgs))
            assert all(m["turn"] == tid for m in turn_msgs)
        else:
            pytest.skip("No turn metadata available")

        # 8) Remove one message and verify it's gone
        to_remove = added[0]["message_ids"][0]
        remove_message(
            agent_role=role,
            agent_id=agent_id,
            message_id=to_remove,
            repo_url=repo_url,
        )
        after_one = list_messages(
            agent_role=role,
            agent_id=agent_id,
            repo_url=repo_url,
        )
        print("TEST DEBUG - After one removed:", pformat(after_one))
        assert to_remove not in {m["message_id"] for m in after_one}

        # 9) Remove all remaining messages one by one and verify empty
        remaining = list_messages(
            agent_role=role,
            agent_id=agent_id,
            repo_url=repo_url,
        )
        for m in remaining:
            remove_message(
                agent_role=role,
                agent_id=agent_id,
                message_id=m["message_id"],
                repo_url=repo_url,
            )
        after_all = list_messages(
            agent_role=role,
            agent_id=agent_id,
            repo_url=repo_url,
        )
        print("TEST DEBUG - After removing all:", pformat(after_all))
        assert after_all == []

    finally:
        # Cleanup only the agent role (no running‐agent endpoint any more)
        print("TEST DEBUG - Deleting agent role")
        delete_agent_role(role)
