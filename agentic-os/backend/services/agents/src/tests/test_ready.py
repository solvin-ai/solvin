# tests/test_ready.py

import pytest
from pprint import pformat

from shared.client_agents import ready

@pytest.mark.order(2)
def test_ready():
    """
    Call the ready endpoint via client_agents.ready(), which returns the unwrapped data dict.
    """
    resp = ready()  # returns {'ready': bool, 'reason': str}
    print(f"TEST DEBUG - ready response: {pformat(resp)}")

    # 1) Response shape
    assert isinstance(resp, dict), f"Expected dict, got {type(resp)}"
    assert "ready" in resp,  f"Missing 'ready' key in response: {resp!r}"
    assert "reason" in resp, f"Missing 'reason' key in response: {resp!r}"

    # 2) No wrapper envelope: resp is the data payload itself
    #    ready must be a bool, reason a non-empty string
    assert isinstance(resp["ready"], bool),   f"'ready' not a boolean: {resp['ready']!r}"
    assert isinstance(resp["reason"], str),   f"'reason' not a string: {resp['reason']!r}"
    assert resp["reason"],                    "'reason' is empty"
