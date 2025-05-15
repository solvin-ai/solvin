# tests/test_execution_all_tools.py

import pytest
from requests.exceptions import HTTPError

from shared.client_tools import tools_list, tools_info, execute_tool

def make_dummy_input(properties: dict) -> dict:
    """
    Given a JSON‐schema 'properties' dict, produce a dummy input payload
    that satisfies basic typing. Unknown or required‐missing fields may
    still cause application‐level errors, which is acceptable.
    """
    args = {}
    for name, schema in properties.items():
        t = schema.get("type")
        if t == "string":
            args[name] = "dummy"
        elif t == "integer":
            args[name] = 0
        elif t == "number":
            args[name] = 0.0
        elif t == "boolean":
            args[name] = False
        elif t == "array":
            args[name] = []
        elif t == "object":
            args[name] = {}
        else:
            # default fallback
            args[name] = None
    return args

def test_execute_all_tools_with_dummy_input():
    """
    For each registered tool:
      1. fetch its schema
      2. build a dummy input
      3. call execute_tool (now with repo_url + repo_name)
      4. assert that we get back a dict with a 'status' key,
         whose value is one of 'success', 'failure', or 'error'.
    """
    tools = tools_list()
    assert tools, "No tools registered to test"

    # this can be any string that your Tools service will accept as repo_url
    dummy_repo_url  = "https://github.com/test-owner/dynamic-repo.git"
    dummy_repo_name = "dynamic-repo"
    dummy_owner     = "test-owner"

    for entry in tools:
        name = entry["tool_name"]

        # 1) fetch schema
        try:
            schema = tools_info(tool_name=name, meta=False, schema=True)
        except HTTPError as he:
            pytest.skip(f"Could not fetch schema for tool '{name}': {he}")

        props = schema.get("properties", {})
        dummy_args = make_dummy_input(props)

        # 2) execute with all four context params: repo_url, repo_name, repo_owner, metadata
        try:
            res = execute_tool(
                tool_name=name,
                input_args=dummy_args,
                repo_url=dummy_repo_url,
                repo_name=dummy_repo_name,
                repo_owner=dummy_owner,
                metadata={}
            )
        except HTTPError as he:
            pytest.fail(f"Transport‐level error executing tool '{name}': {he}")

        # 3) assertions on the returned envelope
        assert isinstance(res, dict), f"Expected dict for '{name}', got {type(res)}"
        assert "status" in res, f"No 'status' in response for '{name}'"
        assert res["status"] in ("success", "failure", "error"), (
            f"Unexpected status '{res['status']}' for '{name}'"
        )

        # Optional: if success, sanity‐check there's a response block
        if res["status"] == "success":
            assert "response" in res and isinstance(res["response"], dict), (
                f"No 'response' dict on success for '{name}'"
            )
