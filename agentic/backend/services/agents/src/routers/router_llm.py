# routers/router_llm.py

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import time

from shared.config import config
from modules.agents_running import add_running_agent
from modules.agent_context import set_current_agent

router = APIRouter(
    prefix="/messages",
    tags=["LLM"],
)

class RunToCompletionRequest(BaseModel):
    agent_role:  str
    agent_id:    Optional[str] = None
    repo_url:   Optional[str] = None
    user_prompt: Optional[str] = ""

@router.post("/run_to_completion")
def messages_run_to_completion(
    payload: RunToCompletionRequest = Body(...)
) -> Dict[str, Any]:
    # 1) Validate required fields
    if not payload.agent_role:
        raise HTTPException(status_code=400, detail="Missing 'agent_role'")
    repo_url = payload.repo_url or config.get("REPO_URL", "")
    if not repo_url:
        raise HTTPException(status_code=400, detail="Missing 'repo_url'")

    # 2) Allocate or reuse a running-agent ID
    agent_id = payload.agent_id
    if not agent_id:
        raw = add_running_agent(payload.agent_role, repo_url)
        if isinstance(raw, dict):
            agent_id = raw.get("agent_id") or raw.get("id")
        else:
            agent_id = raw
        if not agent_id:
            raise HTTPException(
                status_code=500,
                detail="add_running_agent() did not return an agent_id"
            )

    # 3) Set the current agent context
    set_current_agent(payload.agent_role, agent_id, repo_url)

    # ------------------------------------------------------------------
    # STUBBED RESPONSE
    # ------------------------------------------------------------------
    start = time.time()
    response = payload.user_prompt or ""
    total_time = time.time() - start

    result = {
        "agent_id":   agent_id,
        "agent_role": payload.agent_role,
        "status":     "success",
        "response":   response,
        "total_time": total_time,
    }
    return {"data": result, "meta": None, "errors": []}


class SubmitToLLMRequest(BaseModel):
    agent_role:  str
    agent_id:    Optional[str] = None
    repo_url:   Optional[str] = None

@router.post("/submit_to_llm")
def messages_submit_to_llm(
    payload: SubmitToLLMRequest = Body(...)
) -> Dict[str, Any]:
    # 1) Validate required fields
    if not payload.agent_role:
        raise HTTPException(status_code=400, detail="Missing 'agent_role'")
    repo_url = payload.repo_url or config.get("REPO_URL", "")
    if not repo_url:
        raise HTTPException(status_code=400, detail="Missing 'repo_url'")

    # 2) Allocate or reuse a running-agent ID
    agent_id = payload.agent_id
    if not agent_id:
        raw = add_running_agent(payload.agent_role, repo_url)
        if isinstance(raw, dict):
            agent_id = raw.get("agent_id") or raw.get("id")
        else:
            agent_id = raw
        if not agent_id:
            raise HTTPException(
                status_code=500,
                detail="add_running_agent() did not return an agent_id"
            )

    # 3) Set the current agent context
    set_current_agent(payload.agent_role, agent_id, repo_url)

    # ------------------------------------------------------------------
    # STUBBED SINGLE TURN
    # ------------------------------------------------------------------
    # We return a fake turn-1 with an assistant message of "echo".
    turn_meta = {"turn": 1}
    tool_meta = {}
    messages  = {"assistant": {"raw": {"content": "echo"}}}

    payload_out = {
        "turn_meta": turn_meta,
        "tool_meta": tool_meta,
        "messages":  messages,
    }
    return {"data": payload_out, "meta": None, "errors": []}