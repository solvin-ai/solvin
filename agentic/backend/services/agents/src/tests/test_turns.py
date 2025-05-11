# tests/test_turns.py

import pytest
from datetime import datetime, timedelta
import shared.client_agents as client
import requests

# --- Dummy data setup --------------------------------------------

class DummyTurn:
    def __init__(
        self,
        turn: int,
        tool_name: str,
        status: str,
        deleted: bool,
        total_char_count: int,
        ts_assistant: str,
        ts_tool: str
    ):
        # simulate the JSON shape your client returns
        self.turn_meta = {
            "turn": turn,
            "total_char_count": total_char_count
        }
        self.tool_meta = {
            "tool_name": tool_name,
            "status": status,
            "deleted": deleted,
        }
        self.messages = {
            "assistant": {
                "meta": {
                    "timestamp": ts_assistant,
                    "char_count": total_char_count // 2
                },
                "raw": {}
            },
            "tool": {
                "meta": {
                    "timestamp": ts_tool,
                    "char_count": total_char_count // 2
                },
                "raw": {}
            }
        }

BASE_TS = datetime(2023, 1, 1, 12, 0, 0)
DUMMY_TURNS = [
    DummyTurn(
        turn=1,
        tool_name="toolA",
        status="ok",
        deleted=False,
        total_char_count=2048,
        ts_assistant=(BASE_TS + timedelta(seconds=0)).isoformat(),
        ts_tool=(BASE_TS + timedelta(seconds=1)).isoformat(),
    ),
    DummyTurn(
        turn=2,
        tool_name="toolB",
        status="fail",
        deleted=True,
        total_char_count=1024,
        ts_assistant=(BASE_TS + timedelta(seconds=2)).isoformat(),
        ts_tool=(BASE_TS + timedelta(seconds=3)).isoformat(),
    ),
    DummyTurn(
        turn=3,
        tool_name="toolA",
        status="ok",
        deleted=False,
        total_char_count=512,
        ts_assistant=(BASE_TS + timedelta(seconds=4)).isoformat(),
        ts_tool=(BASE_TS + timedelta(seconds=5)).isoformat(),
    ),
]

# --- Fixture that patches requests.get in the client ------------

@pytest.fixture(autouse=True)
def patch_requests(monkeypatch):
    """
    Monkeypatch client.requests.get so that any GET to
      /turns/list  or  /turns/get
    returns exactly the JSON shape client_agents expects.
    """
    # A tiny fake Response object
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

        def raise_for_status(self):
            if not (200 <= self.status_code < 300):
                raise requests.exceptions.HTTPError(
                    f"{self.status_code} Error", response=self
                )

    def fake_get(url, params=None, headers=None):
        # handle /turns/list
        if url.endswith("/turns/list"):
            # start with all turns
            filtered = list(DUMMY_TURNS)

            # filters
            if params.get("filter.status") is not None:
                filtered = [
                    ut for ut in filtered
                    if ut.tool_meta["status"] == params["filter.status"]
                ]
            if params.get("filter.toolName") is not None:
                filtered = [
                    ut for ut in filtered
                    if ut.tool_meta["tool_name"] == params["filter.toolName"]
                ]
            if params.get("filter.deleted") is not None:
                val = params["filter.deleted"].lower() == "true"
                filtered = [ut for ut in filtered if ut.tool_meta["deleted"] == val]
            if params.get("filter.startTime") or params.get("filter.endTime"):
                start = params.get("filter.startTime")
                end   = params.get("filter.endTime")
                start_dt = datetime.fromisoformat(start) if start else None
                end_dt   = datetime.fromisoformat(end)   if end   else None

                def in_range(ut: DummyTurn):
                    for msg in ut.messages.values():
                        ts = msg["meta"]["timestamp"]
                        dt = datetime.fromisoformat(ts)
                        if start_dt and dt < start_dt:
                            continue
                        if end_dt and dt > end_dt:
                            continue
                        return True
                    return False

                filtered = [ut for ut in filtered if in_range(ut)]

            # sorting
            if params.get("sort"):
                fields = [f.strip() for f in params["sort"].split(",")]
                for field in reversed(fields):
                    desc = field.startswith("-")
                    key = field[1:] if desc else field
                    def keyfn(u: DummyTurn):
                        return u.tool_meta.get(key) or u.turn_meta.get(key)
                    filtered.sort(key=keyfn, reverse=desc)

            # pagination
            limit  = int(params.get("limit", 50))
            offset = int(params.get("offset", 0))
            page   = filtered[offset : offset + limit]

            # build payload
            data = {
                "turns": [
                    {
                        "turnMeta": ut.turn_meta,
                        "toolMeta": ut.tool_meta,
                        "messages": ut.messages,
                    }
                    for ut in page
                ],
                # totalContextKb = sum total_char_count / 1024
                "totalContextKb": sum(ut.turn_meta["total_char_count"] for ut in filtered) / 1024.0
            }
            envelope = {
                "data":   data,
                "meta":   {"total": len(filtered), "limit": limit, "offset": offset},
                "errors": []
            }
            return FakeResponse(envelope, status_code=200)

        # handle /turns/get
        if url.endswith("/turns/get"):
            req_turn = int(params["turn"])
            for ut in DUMMY_TURNS:
                if ut.turn_meta["turn"] == req_turn:
                    envelope = {
                        "data": {
                            "turnMeta": ut.turn_meta,
                            "toolMeta": ut.tool_meta,
                            "messages": ut.messages
                        },
                        "meta": None,
                        "errors": []
                    }
                    return FakeResponse(envelope, status_code=200)
            # not found
            return FakeResponse({"data": None}, status_code=404)

        raise RuntimeError(f"Unexpected URL in fake_get: {url!r}")

    # patch it into the client
    monkeypatch.setattr(client.requests, "get", fake_get)
    yield


# --- Tests -------------------------------------------------------

def test_list_turns_basic():
    result = client.list_turns("foo", "run123", "myrepo")
    assert isinstance(result, dict)
    turns = result["turns"]
    assert isinstance(turns, list) and len(turns) == 3

    # totalContextKb = (2048 + 1024 + 512) / 1024 = 3.5
    expected_kb = (2048 + 1024 + 512) / 1024
    assert pytest.approx(result["totalContextKb"], rel=1e-3) == expected_kb


def test_pagination():
    result = client.list_turns("foo", "run123", "myrepo", limit=2, offset=1)
    turns = result["turns"]
    assert len(turns) == 2
    assert turns[0]["turnMeta"]["turn"] == 2
    assert turns[1]["turnMeta"]["turn"] == 3


def test_filter_status_and_toolname_and_deleted():
    # status="ok", toolName="toolA", deleted=False → turns 1 and 3
    result = client.list_turns(
        "foo", "run123", "myrepo",
        status="ok", toolName="toolA", deleted=False
    )
    assert {t["turnMeta"]["turn"] for t in result["turns"]} == {1, 3}

    # status="fail" → turn 2 only
    result2 = client.list_turns("foo", "run123", "myrepo", status="fail")
    assert [t["turnMeta"]["turn"] for t in result2["turns"]] == [2]


def test_filter_time_window():
    start = (BASE_TS + timedelta(seconds=2)).isoformat()
    end   = (BASE_TS + timedelta(seconds=4)).isoformat()
    result = client.list_turns(
        "foo", "run123", "myrepo",
        startTime=start, endTime=end
    )
    assert {t["turnMeta"]["turn"] for t in result["turns"]} == {2, 3}


def test_sorting_desc_turn():
    result = client.list_turns("foo", "run123", "myrepo", sort="-turn")
    assert [t["turnMeta"]["turn"] for t in result["turns"]] == [3, 2, 1]


def test_get_turn_found():
    t = client.get_turn("foo", "run123", "myrepo", 2)
    assert t["turnMeta"]["turn"] == 2
    assert t["toolMeta"]["tool_name"] == "toolB"


def test_get_turn_not_found():
    with pytest.raises(requests.exceptions.HTTPError) as exc:
        client.get_turn("foo", "run123", "myrepo", 999)
    err = exc.value
    assert hasattr(err, "response") and err.response.status_code == 404