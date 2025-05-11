# tests/test_health.py

def test_health(client):
    resp = client.health()
    assert resp["status"] == "ok"

def test_ready(client):
    resp = client.ready()
    assert resp["status"] == "ok"

def test_status(client):
    resp = client.status()
    assert resp["status"] == "ok"
    data = resp["data"]
    # uptime should be non‐negative, requests an int, version a string…
    assert data["uptime_seconds"] >= 0
    assert isinstance(data["requests"], int)
    assert "version" in data
