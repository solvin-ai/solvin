# tests/test_agents_registry.py

import pytest
from pprint import pformat
import json
from requests.exceptions import HTTPError

from shared.client_agents import (
    list_registry,
    upsert_agent_role,
    delete_agent_role,
    get_agent_role,
)

@pytest.mark.order(5)
def test_agents_registry():
    role        = "unit_test_registry"
    description = "Unit test registry agent"
    tools       = ["test-tool-1"]
    prompt      = "You are a registry test agent."

    # 1) List registry at start
    reg1 = list_registry()
    assert isinstance(reg1, list), f"Expected list from list_registry(), got {type(reg1)}"
    print(f"TEST DEBUG - Registry at start: {pformat(reg1)}")

    # 2) Add new agent to registry
    new_entry = upsert_agent_role(role, description, tools, prompt)
    assert isinstance(new_entry, dict), f"Expected dict from upsert_agent_role(), got {type(new_entry)}"
    print(f"TEST DEBUG - Registry add resp: {pformat(new_entry)}")
    assert new_entry["agent_role"] == role

    # 2a) GET via get_agent_role
    got = get_agent_role(role)
    assert isinstance(got, dict)
    assert got["agent_role"] == role

    # 3) List registry again and find our entry
    reg2 = list_registry()
    print(f"TEST DEBUG - Registry after add: {pformat(reg2)}")
    found = next((e for e in reg2 if e["agent_role"] == role), None)
    assert found is not None, f"Newly upserted role {role} not found in registry"

    # 4) Update a property (prompt) of the new agent
    updated_prompt = "You are a very helpful registry test agent."
    print("TEST DEBUG - Updating agent prompt")
    allowed_tools = found["allowed_tools"]
    if isinstance(allowed_tools, str):
        allowed_tools = json.loads(allowed_tools)
    updated_entry = upsert_agent_role(role, description, allowed_tools, updated_prompt)
    assert isinstance(updated_entry, dict)
    print(f"TEST DEBUG - Registry update resp: {pformat(updated_entry)}")
    assert updated_entry["default_developer_prompt"] == updated_prompt

    # 5) Add an allowed tool
    print("TEST DEBUG - Add allowed tool")
    tools_plus = allowed_tools + ["test-tool-2"]
    add_tool_entry = upsert_agent_role(role, description, tools_plus, updated_prompt)
    assert isinstance(add_tool_entry, dict)
    print(f"TEST DEBUG - Registry after adding allowed tool: {pformat(add_tool_entry)}")
    atools = add_tool_entry["allowed_tools"]
    if isinstance(atools, str):
        atools = json.loads(atools)
    assert "test-tool-2" in atools

    # 6) Remove an allowed tool ("test-tool-1")
    print("TEST DEBUG - Remove allowed tool")
    tools_minus = [t for t in atools if t != "test-tool-1"]
    remove_tool_entry = upsert_agent_role(role, description, tools_minus, updated_prompt)
    assert isinstance(remove_tool_entry, dict)
    print(f"TEST DEBUG - Registry after removing allowed tool: {pformat(remove_tool_entry)}")
    rtools = remove_tool_entry["allowed_tools"]
    if isinstance(rtools, str):
        rtools = json.loads(rtools)
    assert "test-tool-1" not in rtools

    # 7) Get the agent details via list before final delete
    reg3 = list_registry()
    print(f"TEST DEBUG - Registry before final delete: {pformat(reg3)}")
    details = next((e for e in reg3 if e["agent_role"] == role), None)
    assert details is not None
    print(f"TEST DEBUG - Details of modified agent: {pformat(details)}")

    # 8) Delete agent using agent_role
    print("TEST DEBUG - Deleting agent")
    del_data = delete_agent_role(role)
    assert isinstance(del_data, dict)
    assert "message" in del_data and role in del_data["message"]
    print(f"TEST DEBUG - Registry delete resp: {pformat(del_data)}")

    # 9) List registry to confirm deletion
    reg4 = list_registry()
    print(f"TEST DEBUG - Registry after delete: {pformat(reg4)}")
    assert not any(e["agent_role"] == role for e in reg4), f"Role {role} still present after deletion"

    # 10) get_agent_role on deleted role should 404
    with pytest.raises(HTTPError):
        get_agent_role(role)


@pytest.mark.order(6)
def test_get_agent_role_nonexistent_raises():
    # Ensure get_agent_role on a role that never existed raises HTTPError
    with pytest.raises(HTTPError):
        get_agent_role("does_not_exist_role")


#
# New tests for upsert_agent_role edge‐cases
#

OPTION_ROLE        = "unit_test_registry_optionals"
OPTION_DESC        = "Testing optional params"
OPTION_TOOLS       = ["opt-tool-1", "opt-tool-2"]
OPTION_PROMPT      = "Optional prompt"
OPTION_MODEL_ID    = "model-123"
OPTION_MODEL       = "fancy-model"
OPTION_REASONING   = "deep"
OPTION_TOOL_CHOICE = "auto"

@pytest.fixture(autouse=True)
def cleanup_option_role():
    # Ensure the optional‐role is deleted before and after each test
    try:
        delete_agent_role(OPTION_ROLE)
    except HTTPError:
        pass
    yield
    try:
        delete_agent_role(OPTION_ROLE)
    except HTTPError:
        pass

@pytest.mark.order(7)
def test_tools_as_json_string():
    # Pass tools as a JSON string instead of a Python list
    upsert_agent_role(
        role=OPTION_ROLE,
        description=OPTION_DESC,
        tools=json.dumps(OPTION_TOOLS),
        prompt=OPTION_PROMPT,
    )
    rec = get_agent_role(OPTION_ROLE)
    atools = rec["allowed_tools"]
    # Should have been deserialized by the client
    assert isinstance(atools, list)
    assert atools == OPTION_TOOLS

@pytest.mark.order(8)
def test_optional_arguments_roundtrip():
    # Pass all optional parameters through upsert_agent_role
    upsert_agent_role(
        role=OPTION_ROLE,
        description=OPTION_DESC,
        tools=OPTION_TOOLS,
        prompt=OPTION_PROMPT,
        model_id=OPTION_MODEL_ID,
        model=OPTION_MODEL,
        reasoning_level=OPTION_REASONING,
        tool_choice=OPTION_TOOL_CHOICE,
    )
    rec = get_agent_role(OPTION_ROLE)
    # Verify each optional field round‐trips correctly
    assert rec.get("model_id")        == OPTION_MODEL_ID
    assert rec.get("model")           == OPTION_MODEL
    assert rec.get("reasoning_level") == OPTION_REASONING
    assert rec.get("tool_choice")     == OPTION_TOOL_CHOICE
