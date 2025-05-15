# routers/router_agents_running.py

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from modules.agents_running import (
    list_running_agents       as backend_list_running,
    get_current_running_agent as backend_get_current,
    set_current_agent         as backend_set_current,
    get_agent_stack           as backend_get_stack,
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
    repo_url:  str = Query(..., description="Repository URL")
) -> Dict[str, Any]:
    """
    GET /agents/running/list?repo_url=...
    """
    result = backend_list_running(repo_url)
    return {"data": result, "meta": None, "errors": []}


@router.get("/current")
def get_current_running_agent_endpoint(
    repo_url:  str = Query(..., description="Repository URL")
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


@router.post("/set_current")
def set_current_agent_endpoint(
    payload: RunningAgentPayload = Body(
        ...,
        examples={
            "default": {
                "summary": "Make this agent the CURRENT for the given task",
                "value": {
                    "agent_role": "worker",
                    "agent_id":   "002",
                    "repo_url":   "my_repo"
                }
            }
        }
    )
) -> Dict[str, Any]:
    """
    POST /agents/running/set_current
    body: { agent_role, agent_id, repo_url }
    """
    if not payload.agent_id:
        raise HTTPException(status_code=422, detail="Missing required field: agent_id")
    result = backend_set_current(
        payload.agent_role,
        payload.agent_id,
        payload.repo_url
    )
    return {"data": result, "meta": None, "errors": []}


@router.get("/stack")
def list_agent_call_stack(
    repo_url:  Optional[str] = Query(
        None, description="If provided, only include stack entries for this repo"
    )
) -> Dict[str, Any]:
    """
    GET /agents/running/stack?repo_url=...
    Returns the current nested call‐stack of agents.
    """
    full_stack: List[Dict[str, str]] = backend_get_stack()
    if repo_url is not None :
        stack = [
            e for e in full_stack
            if e["repo_url"] == repo_url
        ]
    else:
        stack = full_stack

    return {"data": stack, "meta": None, "errors": []}

