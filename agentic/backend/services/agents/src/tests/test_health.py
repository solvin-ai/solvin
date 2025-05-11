# tests/test_health.py

import pytest
from pprint import pformat

from shared.client_agents import health

@pytest.mark.order(1)
def test_health():
    """
    Verify the Agents service health endpoint via the client helper.
    The client_agents.health() call unwraps the envelope and returns only the data dict.
    """
    h = health()
    print(f"TEST DEBUG - health response: {pformat(h)}")

    # Check that we got a dict with the expected fields
    assert isinstance(h, dict), f"Expected dict, got {type(h)}"
    assert h.get("status") == "ok", f"Unexpected status: {h.get('status')!r}"
    assert h.get("reason") == "running", f"Unexpected reason: {h.get('reason')!r}"