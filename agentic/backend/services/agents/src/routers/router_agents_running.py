# routers/router_agents_running.py

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from modules.agents_running import (
    list_running_agents       as backend_list_running,
    get_current_running_agent as backend_get_current,
    add_running_agent         as backend_add,
    remove_running_agent      as backend_remove,
    set_current_agent         as backend_set_current,
    get_agent_stack           as backend_get_stack,       # ← new import
)

router = APIRouter(
    prefix="/agents/running",
    tags=["Running Agents"],
)

class RunningAgentPayload(BaseModel):
    agent_role: str
    repo_url:  str
    agent_id:   Optional[str] = None

@router.get("/list")
def list_running_agents_endpoint(
    repo_url: str = Query(..., description="Repository name")
) -> Dict[str, Any]:
    """
    GET /agents/running/list?repo_url=...
    """
    result = backend_list_running(repo_url)
    return {"data": result, "meta": None, "errors": []}

@router.get("/current")
def get_current_running_agent_endpoint(
    repo_url: str = Query(..., description="Repository name")
) -> Dict[str, Any]:
    """
    GET /agents/running/current?repo_url=...
    """
    result = backend_get_current(repo_url)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No current running agent in repo '{repo_url}'"
        )
    return {"data": result, "meta": None, "errors": []}

@router.post("/add")
def add_running_agent_endpoint(
    payload: RunningAgentPayload = Body(
        ...,
        examples={"agent_role": "foo", "repo_url": "my_repo"}
    )
) -> Dict[str, Any]:
    """
    POST /agents/running/add
    body: { agent_role, repo_url }
    """
    result = backend_add(payload.agent_role, payload.repo_url)
    return {"data": result, "meta": None, "errors": []}

@router.post("/remove")
def remove_running_agent_endpoint(
    payload: RunningAgentPayload = Body(
        ...,
        examples={"agent_role": "foo", "agent_id": "002", "repo_url": "my_repo"}
    )
) -> Dict[str, Any]:
    """
    POST /agents/running/remove
    body: { agent_role, agent_id, repo_url }
    """
    if not payload.agent_id:
        raise HTTPException(status_code=422, detail="Missing required field: agent_id")
    result = backend_remove(payload.agent_role, payload.agent_id, payload.repo_url)
    return {"data": result, "meta": None, "errors": []}

@router.post("/set_current")
def set_current_agent_endpoint(
    payload: RunningAgentPayload = Body(
        ...,
        examples={"agent_role": "foo", "agent_id": "002", "repo_url": "my_repo"}
    )
) -> Dict[str, Any]:
    """
    POST /agents/running/set_current
    body: { agent_role, agent_id, repo_url }
    """
    if not payload.agent_id:
        raise HTTPException(status_code=422, detail="Missing required field: agent_id")
    result = backend_set_current(payload.agent_role, payload.agent_id, payload.repo_url)
    return {"data": result, "meta": None, "errors": []}

@router.get("/stack")
def get_running_agent_stack_endpoint() -> Dict[str, Any]:
    """
    GET /agents/running/stack
    Returns the current in-memory call-stack of agents (LIFO order).
    """
    stack: List[Dict[str, Any]] = backend_get_stack()
    return {"data": stack, "meta": None, "errors": []}
