# routers/router_turns.py

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime

from modules.turns_list import get_turns_list
from modules.unified_turn import UnifiedTurn

router = APIRouter(
    prefix="/turns",
    tags=["Turns"],
)


@router.get("/list")
def list_turns(
    agent_role: str = Query(..., description="Agent role"),
    agent_id:   str = Query(..., description="Running-agent ID"),
    repo_url:  str = Query(..., description="Repository name"),
    limit:      int = Query(50, ge=1, description="Max turns to return"),
    offset:     int = Query(0, ge=0, description="Pagination offset"),
    status:     Optional[str]      = Query(None, alias="filter.status",    description="Filter by tool status"),
    tool_name:  Optional[str]      = Query(None, alias="filter.toolName",  description="Filter by tool name"),
    deleted:    Optional[bool]     = Query(None, alias="filter.deleted",   description="Filter by deleted flag"),
    start_time: Optional[datetime] = Query(None, alias="filter.startTime", description="Filter turns with any message ≥ this time"),
    end_time:   Optional[datetime] = Query(None, alias="filter.endTime",   description="Filter turns with any message ≤ this time"),
    sort:       Optional[str]      = Query(None, description="Comma-separated fields to sort by, prefix '-' for desc"),
) -> Dict[str, Any]:
    """
    RPC-style:
      GET /turns/list?
        agent_role=…&
        agent_id=…&
        repo_url=…&
        limit=…&
        offset=…&
        filter.status=…&
        filter.toolName=…&
        filter.deleted=…&
        filter.startTime=…&
        filter.endTime=…&
        sort=…
    """
    # 1) load all turns for this (agent_role, agent_id, repo_url)
    turns: List[UnifiedTurn] = get_turns_list(agent_role, agent_id, repo_url)

    # 2) compute total context size (all turns)
    total_context_kb = sum(
        ut.turn_meta.get("total_char_count", 0) for ut in turns
    ) / 1024.0

    # 3) in‐memory filtering
    def _any_msg_in_range(ut: UnifiedTurn, start: datetime, end: datetime) -> bool:
        for msg in ut.messages.values():
            ts = msg["meta"].get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
            if start and dt < start:
                continue
            if end and dt > end:
                continue
            return True
        return False

    filtered: List[UnifiedTurn] = []
    for ut in turns:
        tm = ut.tool_meta
        if status is not None and tm.get("status") != status:
            continue
        if tool_name is not None and tm.get("tool_name") != tool_name:
            continue
        if deleted is not None and tm.get("deleted") != deleted:
            continue
        if (start_time or end_time) and not _any_msg_in_range(ut, start_time, end_time):
            continue
        filtered.append(ut)

    total = len(filtered)

    # 4) sorting
    if sort:
        fields = [f.strip() for f in sort.split(",")]
        for field in reversed(fields):
            desc = field.startswith("-")
            key = field[1:] if desc else field
            def _keyfn(x: UnifiedTurn):
                return x.tool_meta.get(key) or x.turn_meta.get(key)
            filtered.sort(key=_keyfn, reverse=desc)

    # 5) pagination
    page = filtered[offset : offset + limit]

    # 6) build data items
    data_items = [
        {
            "turnMeta": ut.turn_meta,
            "toolMeta": ut.tool_meta,
            "messages": ut.messages,
        }
        for ut in page
    ]

    # 7) envelope: move totalContextKb into data, keep pagination in meta
    envelope_data = {
        "turns":           data_items,
        "totalContextKb":  round(total_context_kb, 2),
    }
    envelope_meta = {
        "total":  total,
        "limit":  limit,
        "offset": offset,
    }

    return {
        "data":   envelope_data,
        "meta":   envelope_meta,
        "errors": []
    }


@router.get("/get")
def get_turn(
    agent_role: str = Query(..., description="Agent role"),
    agent_id:   str = Query(..., description="Running-agent ID"),
    repo_url:  str = Query(..., description="Repository name"),
    turn:       int = Query(..., description="Turn number"),
) -> Dict[str, Any]:
    """
    RPC-style:
      GET /turns/get?agent_role=…&agent_id=…&repo_url=…&turn=…
    """
    turns = get_turns_list(agent_role, agent_id, repo_url)
    for ut in turns:
        if ut.turn_meta.get("turn") == turn:
            return {
                "data": {
                    "turnMeta": ut.turn_meta,
                    "toolMeta": ut.tool_meta,
                    "messages": ut.messages,
                },
                "meta":   None,
                "errors": []
            }
    raise HTTPException(status_code=404, detail=f"Turn {turn} not found")