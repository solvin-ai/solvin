# routers/router_llm.py

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import time

from shared.config import config
from modules.agents_running import add_running_agent, set_current_agent
from modules.run_agent_task import run_agent_task

router = APIRouter(
    prefix="/llm",
    tags=["LLM"],
)

class RunAgentTaskRequest(BaseModel):
    agent_role:  str
    agent_id:    Optional[str] = None
    repo_url:    Optional[str] = None
    user_prompt: Optional[str] = ""

@router.post("/run_agent_task")
def llm_run_agent_task(
    payload: RunAgentTaskRequest = Body(...)
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
        agent_id = raw.get("agent_id") if isinstance(raw, dict) else raw
        if not agent_id:
            raise HTTPException(
                status_code=500,
                detail="add_running_agent() did not return an agent_id"
            )

    # 3) Set the current agent context
    set_current_agent(payload.agent_role, agent_id, repo_url)

    # 4) Invoke the end-to-end run via our new wrapper
    start = time.time()
    result = run_agent_task(
        agent_role=payload.agent_role,
        agent_id=agent_id,
        repo_url=repo_url,
        user_prompt=payload.user_prompt or ""
    )
    total_time = time.time() - start
    # (you can log total_time if desired)

    # 5) Return wrapped response
    return {
        "data":   result,
        "meta":   None,
        "errors": []
    }


class SubmitToLLMRequest(BaseModel):
    agent_role: str
    agent_id:   Optional[str] = None
    repo_url:   Optional[str] = None

@router.post("/submit_to_llm")
def llm_submit_to_llm(
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
        agent_id = raw.get("agent_id") if isinstance(raw, dict) else raw
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
    # Return a fake assistant echo for simplicity
    turn_meta = {"turn": 1}
    tool_meta = {}
    messages  = {"assistant": {"raw": {"content": "echo"}}}

    return {
        "data": {
            "turn_meta": turn_meta,
            "tool_meta": tool_meta,
            "messages":  messages,
        },
        "meta":   None,
        "errors": []
    }
