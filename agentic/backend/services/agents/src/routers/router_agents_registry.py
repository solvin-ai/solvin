# routers/router_agents_registry.py

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import List, Optional, Union, Any, Dict
import json

from modules.agents_temp_registry import (
    list_registry           as backend_list_registry,
    get_agent_role          as backend_get_agent_role,
    upsert_agent_role       as backend_upsert_agent_role,
    delete_agent_role       as backend_delete_agent_role,
)

router = APIRouter(
    prefix="/agents/registry",
    tags=["Agent Registry"],
)

class AgentRegistryEntry(BaseModel):
    agent_role:               Optional[str]         = None
    agent_description:        Optional[str]         = ""
    allowed_tools:            Union[List[str], str] = "[]"
    default_developer_prompt: Optional[str]         = ""
    model:                    Optional[str]         = None
    reasoning_level:          Optional[str]         = None
    tool_choice:              Optional[str]         = "required"
    message:                  Optional[str]         = None

@router.get("/list", summary="List all registered agent roles")
def list_registry() -> Dict[str, Any]:
    """
    RPC‐style:
      GET /agents/registry/list
    Returns the full, global list of agent‐role registry entries.
    """
    result = backend_list_registry()
    return {"data": result, "meta": None, "errors": []}


@router.get("/get", summary="Get a registry entry by agent_role")
def get_agent_role(
    agent_role: str = Query(..., description="Agent role identifier")
) -> Dict[str, Any]:
    """
    RPC‐style:
      GET /agents/registry/get?agent_role=<role>
    """
    entry = backend_get_agent_role(agent_role)
    if not entry:
        raise HTTPException(status_code=404,
                            detail=f"Agent role '{agent_role}' not found")
    return {"data": entry, "meta": None, "errors": []}


@router.post("/upsert", summary="Add or update an agent‐role registry entry")
def upsert_agent_role(
    entry: AgentRegistryEntry = Body(..., description="Full registry entry")
) -> Dict[str, Any]:
    """
    RPC‐style:
      POST /agents/registry/upsert
      body: AgentRegistryEntry
    """
    data = entry.dict()
    agent_role = data.get("agent_role")
    if not agent_role:
        raise HTTPException(status_code=400,
                            detail="Missing required field: agent_role")

    # allowed_tools may come in as JSON‐string or list
    allowed_tools = data.get("allowed_tools", "[]")
    if isinstance(allowed_tools, str):
        try:
            allowed_tools = json.loads(allowed_tools)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400,
                                detail="allowed_tools must be JSON list or array")

    result = backend_upsert_agent_role(
        agent_role=agent_role,
        agent_description=data.get("agent_description", ""),
        allowed_tools=allowed_tools,
        default_developer_prompt=data.get("default_developer_prompt", ""),
        model=data.get("model"),
        reasoning_level=data.get("reasoning_level"),
        tool_choice=data.get("tool_choice"),
    )
    return {"data": result, "meta": None, "errors": []}


@router.delete("/delete", summary="Delete an agent‐role registry entry")
def delete_agent_role(
    agent_role: str = Query(..., description="Agent role identifier")
) -> Dict[str, Any]:
    """
    RPC‐style:
      DELETE /agents/registry/delete?agent_role=<role>
    """
    result = backend_delete_agent_role(agent_role)
    return {"data": result, "meta": None, "errors": []}