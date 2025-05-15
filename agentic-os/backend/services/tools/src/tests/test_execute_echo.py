# tests/test_execute_echo.py

import pytest
from shared.client_tools import execute_tool, ToolError

def test_execute_echo_success():
    """
    The 'echo' tool should mirror back its input.
    """
    payload = {"input_text": "hello world"}
    data = execute_tool(
        "echo",
        payload,
        # use a real repo that your repos‐service can resolve:
        repo_name="Hello-World",
        repo_owner="octocat",
        metadata={}        # any extra metadata you wish to pass
    )

    # we expect an unwrapped tool‐response dict
    assert isinstance(data, dict)
    assert data.get("status") == "success"     # executor now runs and returns "success"

    resp = data.get("response")
    assert isinstance(resp, dict)
    # The echo tool should include our input text somewhere in its output
    assert "hello world" in str(resp)


def test_execute_echo_not_found():
    """
    Requesting a non-existent tool should raise a ToolError
    with code "TOOL_NOT_FOUND".
    """
    with pytest.raises(ToolError) as exc:
        execute_tool(
            "nope_echo",
            {},
            repo_name="dummy",   # arbitrary—lookup short‐circuits on missing tool
            repo_owner="alice",
            metadata={}
        )
    # Missing tool should surface the TOOL_NOT_FOUND code
    assert exc.value.code == "TOOL_NOT_FOUND"
