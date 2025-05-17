# routers/router_agents_running.py

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List, Tuple

from modules.agents_running import (
    list_running_agents       as backend_list_running,
    get_current_running_agent as backend_get_current,
    set_current_agent         as backend_set_current,
)
from modules.agent_call_graph import (
    get_graph_edges,
    format_mermaid_sequence,
)
from modules.turns_list import get_turns_metadata
from modules.run_agent_task import run_agent_task

router = APIRouter(
    prefix="/agents/running",
    tags=["Running Agents"],
)

#
# Payloads
#

class RunningAgentPayload(BaseModel):
    agent_role: str = Field(..., description="Agent role, e.g. 'SWE' or 'root'")
    repo_url:   str = Field(..., description="Repository URL")
    agent_id:   Optional[str] = Field(
        None,
        description="Optional override of agent_id (e.g. '001' for explicit seeding)"
    )

class RunAgentPayload(BaseModel):
    agent_role:  str               = Field(..., description="Agent role to run")
    repo_url:    str               = Field(..., description="Repository URL")
    user_prompt: str               = Field(
        ...,
        min_length=1,
        description="Non-empty prompt for the agent"
    )
    agent_id:    Optional[str]     = Field(
        None,
        description="Optional override agent_id; if omitted, md5(user_prompt) is used"
    )
    repo_owner:  Optional[str]     = Field(None, description="Optional GitHub repo owner")
    repo_name:   Optional[str]     = Field(None, description="Optional GitHub repo name")

    @validator("user_prompt")
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_prompt must be non-empty")
        return v

#
# Endpoints
#

@router.get("/list")
def list_running_agents_endpoint(
    repo_url: str = Query(..., description="Repository URL")
) -> Dict[str, Any]:
    """
    GET /agents/running/list?repo_url=...
    Returns all running agents in this repo, enriched with their current 'state'
    (one of "idle", "running", "waiting") from the turns_list metadata.
    """
    raw = backend_list_running(repo_url)
    data: List[Dict[str, Any]] = []
    for a in raw:
        meta = get_turns_metadata(a["agent_role"], a["agent_id"], a["repo_url"]) or {}
        state = meta.get("state", "idle")
        a_with_state = a.copy()
        a_with_state["state"] = state
        data.append(a_with_state)
    return {"data": data, "meta": None, "errors": []}


@router.get("/current")
def get_current_running_agent_endpoint(
    repo_url: str = Query(..., description="Repository URL")
) -> Dict[str, Any]:
    """
    GET /agents/running/current?repo_url=...
    Returns the single 'current' agent for this repo, with its 'state'.
    """
    data = backend_get_current(repo_url)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"No current running agent in repo '{repo_url}'"
        )
    meta = get_turns_metadata(data["agent_role"], data["agent_id"], data["repo_url"]) or {}
    data["state"] = meta.get("state", "idle")
    return {"data": data, "meta": None, "errors": []}


@router.post("/set_current")
def set_current_agent_endpoint(
    payload: RunningAgentPayload
) -> Dict[str, Any]:
    """
    POST /agents/running/set_current
    body: { agent_role, agent_id, repo_url }
    """
    if not payload.agent_id:
        raise HTTPException(status_code=422, detail="Missing required field: agent_id")

    backend_set_current(
        payload.agent_role,
        payload.agent_id,
        payload.repo_url
    )

    meta = get_turns_metadata(payload.agent_role, payload.agent_id, payload.repo_url) or {}
    return {
        "data": {
            "agent_role": payload.agent_role,
            "agent_id":   payload.agent_id,
            "repo_url":   payload.repo_url,
            "state":      meta.get("state", "idle"),
        },
        "meta": None,
        "errors": []
    }


@router.post("/run")
def run_agent_endpoint(
    payload: RunAgentPayload
) -> Dict[str, Any]:
    """
    POST /agents/running/run
    body: {
      agent_role:  string,
      repo_url:    string,
      user_prompt: string,            # required, non-empty
      agent_id?:   string,            # optional override
      repo_owner?: string,
      repo_name?:  string
    }
    Always requires a non-empty user_prompt.  If agent_id is omitted,
    it will be computed as md5(user_prompt) by seed_agent().
    """
    try:
        result = run_agent_task(
            agent_role=payload.agent_role,
            repo_url=payload.repo_url,
            user_prompt=payload.user_prompt,
            agent_id=payload.agent_id,
            repo_owner=payload.repo_owner,
            repo_name=payload.repo_name,
        )
    except ValueError as e:
        # user_prompt was empty or invalid
        raise HTTPException(status_code=422, detail=str(e))

    return {"data": result, "meta": None, "errors": []}


@router.get("/graph")
def get_agent_call_graph_endpoint(
    format: str = Query(
        "json",
        enum=["json", "mermaid", "graphviz"],
        description="Output format"
    )
) -> Dict[str, Any]:
    """
    GET /agents/running/graph?format={json,mermaid,graphviz}
    - json     → [[parent_role, parent_id], [child_role, child_id], ...]
    - mermaid  → Mermaid sequenceDiagram DSL
    - graphviz → Graphviz DOT source
    """
    edges = get_graph_edges()

    if format == "json":
        data = [[list(p), list(c)] for p, c in edges]
        return {"data": data, "meta": None, "errors": []}

    if format == "mermaid":
        data = format_mermaid_sequence()
        return {"data": data, "meta": None, "errors": []}

    if format == "graphviz":
        lines: List[str] = [
            "digraph AgentSpawn {",
            "  rankdir=LR;",
            "  labelloc=\"t\";",
            "  label=\"Agent Spawn Graph\";",
        ]
        for (pr, pi), (cr, ci) in edges:
            src = f"\"{pr}_{pi[:8]}\""
            dst = f"\"{cr}_{ci[:8]}\""
            lines.append(f"  {src} -> {dst};")
        lines.append("}")
        return {"data": "\n".join(lines), "meta": None, "errors": []}

    # Should be unreachable thanks to Query enum
    raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
