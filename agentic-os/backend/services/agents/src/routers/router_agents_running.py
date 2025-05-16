# routers/router_agents_running.py

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from modules.agents_running import (
    list_running_agents       as backend_list_running,
    get_current_running_agent as backend_get_current,
    set_current_agent         as backend_set_current,
)
from modules.agent_call_graph import (
    get_graph_edges,
    format_mermaid_sequence,
)

router = APIRouter(
    prefix="/agents/running",
    tags=["Running Agents"],
)

class RunningAgentPayload(BaseModel):
    agent_role: str
    repo_url:   str
    agent_id:   Optional[str] = None

@router.get("/list")
def list_running_agents_endpoint(
    repo_url: str = Query(..., description="Repository URL")
) -> Dict[str, Any]:
    """
    GET /agents/running/list?repo_url=...
    """
    data = backend_list_running(repo_url)
    return {"data": data, "meta": None, "errors": []}

@router.get("/current")
def get_current_running_agent_endpoint(
    repo_url: str = Query(..., description="Repository URL")
) -> Dict[str, Any]:
    """
    GET /agents/running/current?repo_url=...
    """
    data = backend_get_current(repo_url)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"No current running agent in repo '{repo_url}'"
        )
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
    data = backend_set_current(
        payload.agent_role,
        payload.agent_id,
        payload.repo_url
    )
    return {"data": data, "meta": None, "errors": []}

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
        # each edge as two two‐item lists
        data = [ [list(p), list(c)] for p, c in edges ]
        return {"data": data, "meta": None, "errors": []}

    if format == "mermaid":
        # full mermaid DSL as one string
        data = format_mermaid_sequence()
        return {"data": data, "meta": None, "errors": []}

    if format == "graphviz":
        # build DOT
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
        data = "\n".join(lines)
        return {"data": data, "meta": None, "errors": []}

    # should be unreachable thanks to enum
    raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
