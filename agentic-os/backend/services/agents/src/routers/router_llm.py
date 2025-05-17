# routers/router_llm.py

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from modules.run_agent_task import run_agent_task

router = APIRouter(
    prefix="/llm",
    tags=["LLM"],
)

class RunAgentTaskRequest(BaseModel):
    agent_role:  str           = Field(
        ..., min_length=1, description="Agent role, e.g. 'SWE'"
    )
    repo_url:    str           = Field(
        ..., min_length=1, description="Repository URL"
    )
    user_prompt: str           = Field(
        ..., min_length=1, description="Non-empty user prompt"
    )
    agent_id:    Optional[str] = Field(
        None,
        description="Optional explicit agent_id; if omitted, MD5(user_prompt) will be used"
    )

@router.post("/run_agent_task")
def llm_run_agent_task(
    payload: RunAgentTaskRequest = Body(...)
) -> Dict[str, Any]:
    """
    Full workflow:
      • user_prompt is required (min_length=1)
      • agent_id if omitted → MD5(user_prompt) (inside run_agent_task)
      • seeding & thread-local context happens inside run_agent_task
    """
    try:
        result = run_agent_task(
            agent_role=payload.agent_role,
            repo_url=payload.repo_url,
            user_prompt=payload.user_prompt,
            agent_id=payload.agent_id,
        )
    except ValueError as e:
        # e.g. empty prompt (shouldn't happen thanks to Pydantic) or
        # invalid agent_id
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"data": result, "meta": None, "errors": []}


class SubmitToLLMRequest(BaseModel):
    agent_role: str           = Field(
        ..., min_length=1, description="Agent role, e.g. 'SWE'"
    )
    repo_url:   str           = Field(
        ..., min_length=1, description="Repository URL"
    )
    agent_id:   Optional[str] = Field(
        None,
        description="Explicit agent_id if known"
    )

@router.post("/submit_to_llm")
def llm_submit_to_llm(
    payload: SubmitToLLMRequest = Body(...)
) -> Dict[str, Any]:
    """
    Stub for a single-turn LLM call.  Does _not_ seed or set current agent.
    """
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
