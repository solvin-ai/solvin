# test_tools.py

import pytest
from requests.exceptions import HTTPError

from shared.client_tools import (
    health,
    ready,
    status       as tools_status,
    list_tools,
    tools_info,
    execute_tool,
    execute_tools_bulk,
)

@pytest.fixture
def tools_list():
    return list_tools()

# 1) Basic health/ready/status/list probes

def test_health_check():
    resp = health()
    assert resp.get("status") == "ok"

def test_ready_check():
    resp = ready()
    assert resp.get("status") == "ready"

def test_status_check():
    st = tools_status()
    assert st.get("status") == "ok"
    assert isinstance(st.get("uptime_seconds"), int)
    assert isinstance(st.get("requests"), int)
    assert isinstance(st.get("tool_count"), int)

def test_list_tools(tools_list):
    assert isinstance(tools_list, list) and tools_list
    for t in tools_list:
        assert "tool_name" in t and isinstance(t["tool_name"], str)

# 2) tools_info: single, bulk, flag combinations, errors

def test_tools_info_single_and_bulk(tools_list):
    first = tools_list[0]["tool_name"]
    one = tools_info(tool_name=first)
    assert isinstance(one, dict)

    names = [t["tool_name"] for t in tools_list]
    bulk = tools_info(tool_names=names)
    assert isinstance(bulk, dict)
    assert set(bulk.keys()) == set(names)

def test_tools_info_meta_schema_combinations(tools_list):
    n = tools_list[0]["tool_name"]
    assert isinstance(tools_info(tool_name=n, meta=True,  schema=False), dict)
    assert isinstance(tools_info(tool_name=n, meta=False, schema=True), dict)
    assert isinstance(tools_info(tool_name=n, meta=True,  schema=True), dict)
    neither = tools_info(tool_name=n, meta=False, schema=False)
    assert isinstance(neither, dict) and not neither

def test_tools_info_no_args_raises():
    with pytest.raises(ValueError):
        tools_info()

def test_tools_info_not_found_raises():
    with pytest.raises(HTTPError):
        tools_info(tool_name="no_such_tool_abc")

# 3) execute_tool: missing tool vs. application‐level error

def test_execute_tool_not_found_raises():
    with pytest.raises(HTTPError):
        execute_tool("no_such_tool_abc", {}, repo_name="dummy")

def test_execute_tool_application_error(tools_list):
    name = tools_list[0]["tool_name"]
    res = execute_tool(name, {}, repo_name="dummy")
    assert isinstance(res, dict)
    assert res.get("status") in ("error", "failure")

# 4) execute_tools_bulk: transport errors vs. per‐item statuses

def test_execute_bulk_transport_error():
    # totally malformed body → HTTP 422
    with pytest.raises(HTTPError):
        execute_tools_bulk([{"foo": "bar"}])

def test_execute_bulk_application_error_single(tools_list):
    name = tools_list[0]["tool_name"]
    resp = execute_tools_bulk([
        {"tool_name": name, "input_args": {}, "repo_name": "r"}
    ])
    assert isinstance(resp, list) and len(resp) == 1
    assert resp[0].get("status") in ("error", "failure")

def test_execute_bulk_mixed_valid_and_invalid(tools_list):
    valid   = {"tool_name": tools_list[0]["tool_name"], "input_args": {}, "repo_name": "r1"}
    invalid = {"tool_name": "nope_123",                         "input_args": {}, "repo_name": "r2"}
    resp = execute_tools_bulk([valid, invalid])
    assert isinstance(resp, list) and len(resp) == 2
    # first item may succeed or error; second must be error
    assert resp[1]["status"] in ("error", "failure")