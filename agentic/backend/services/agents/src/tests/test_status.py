# tests/test_status.py

import pytest
from pprint import pformat

from shared.client_agents import status

@pytest.mark.order(3)
def test_status_endpoint():
    """
    Verify the status() client returns only the service status payload (no envelope),
    and that it contains the expected keys and omits any health/readiness fields.
    """
    data = status()
    print(f"TEST DEBUG - status response: {pformat(data)}")

    # These keys must be present in the status payload
    assert "claimed_repo"   in data
    assert "repo_state"     in data
    assert "uptime_seconds" in data
    assert "api_requests"   in data
    assert "version"        in data

    # These keys should NOT be present (they belong to /health or /ready)
    for forbidden in ("status", "reason", "ready", "service_ready"):
        assert forbidden not in data, f"Unexpected key '{forbidden}' found in status response"
