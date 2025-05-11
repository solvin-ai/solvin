# tests/test_health_status_list.py

from shared.client_tools import health, ready, status, tools_list

def test_health():
    r = health()
    assert isinstance(r, dict)
    assert r.get("status") == "ok"

def test_ready():
    r = ready()
    assert isinstance(r, dict)
    assert r.get("status") == "ready"

def test_status():
    st = status()
    assert isinstance(st, dict)
    assert st.get("status") == "ok"
    assert isinstance(st.get("uptime_seconds"), int)
    assert isinstance(st.get("requests"), int)
    assert isinstance(st.get("tool_count"), int)

def test_tools_list():
    ts = tools_list()
    assert isinstance(ts, list)
    assert ts, "Expected at least one tool"
    for t in ts:
        assert "tool_name" in t and isinstance(t["tool_name"], str)
