# routers/router_execute.py

import time
import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator

from shared.logger import logger
from modules.tools_jetstream_pub import publish_exec_request
from modules.tools_executor import execute_tool
from modules.tools_registry import get_global_registry
from modules.routers_utils import object_to_dict

router = APIRouter(tags=["Tools"])


class ExecuteRequest(BaseModel):
    tool_name: str
    input_args: Dict[str, Any]
    repo_url: str
    repo_name: Optional[str] = Field(None, description="Repo name (derived from URL if missing)")
    repo_owner: Optional[str] = Field(None, description="Repo owner (derived from URL if missing)")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    turn_id: Optional[str] = None
    reply_to: Optional[str] = None

    @validator("repo_name", pre=True, always=True)
    def _default_repo_name(cls, v, values):
        if v is None:
            url = values.get("repo_url", "")
            parts = url.rstrip("/").split("/")
            if parts:
                return parts[-1]
        return v

    @validator("repo_owner", pre=True, always=True)
    def _default_repo_owner(cls, v, values):
        if v is None:
            url = values.get("repo_url", "")
            parts = url.rstrip("/").split("/")
            if len(parts) >= 2:
                return parts[-2]
        return v


class BulkExecuteRequest(BaseModel):
    requests: List[ExecuteRequest]


@router.post(
    "/tools/execute",
    summary="Publish a tool execution request to JetStream (non-blocking)"
)
async def execute_tool_nonblocking(request: ExecuteRequest):
    t0_total = time.monotonic()
    logger.debug("ENTER /tools/execute tool=%s turn_id=%s",
                 request.tool_name, request.turn_id)

    # Ensure repo_name and repo_owner were derived
    if not request.repo_name or not request.repo_owner:
        raise HTTPException(
            status_code=400,
            detail="Could not derive repo_name/repo_owner from repo_url"
        )

    registry = get_global_registry()
    if request.tool_name not in registry:
        logger.debug("TOOL_NOT_FOUND %s", request.tool_name)
        raise HTTPException(status_code=404,
                            detail=f"Tool '{request.tool_name}' not found")

    payload = request.dict()
    logger.debug("Prepared payload keys=%s", list(payload.keys()))

    t0_pub = time.monotonic()
    try:
        ack = await publish_exec_request(payload)
    except Exception as e:
        t_pub_err = (time.monotonic() - t0_pub) * 1000
        logger.error("publish_exec_request FAILED after %.1fms: %s",
                     t_pub_err, e, exc_info=True)
        raise HTTPException(status_code=500,
                            detail="Failed to enqueue execution request")
    t_pub = (time.monotonic() - t0_pub) * 1000
    logger.debug(
        "publish_exec_request SUCCEEDED in %.1fms ack=(stream=%s, seq=%s)",
        t_pub, getattr(ack, "stream", None), getattr(ack, "seq", None)
    )

    response = {"status": "ok", "data": {"stream": ack.stream, "seq": ack.seq}}
    t_total = (time.monotonic() - t0_total) * 1000
    logger.debug("EXIT /tools/execute total=%.1fms response=%s", t_total, response)
    return response


@router.post(
    "/tools/execute-blocking",
    summary="Execute a single tool (blocking)"
)
def execute_tool_blocking(request: ExecuteRequest):
    registry = get_global_registry()
    if request.tool_name not in registry:
        return {
            "status": "error",
            "response": None,
            "error": {
                "code": "TOOL_NOT_FOUND",
                "message": f"Tool '{request.tool_name}' not found"
            }
        }

    try:
        result = execute_tool(
            tool_name=request.tool_name,
            input_args=request.input_args,
            repo_url=request.repo_url,
            repo_name=request.repo_name,
            repo_owner=request.repo_owner,
            metadata=request.metadata or {},
            turn_id=request.turn_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unhandled exception in /tools/execute-blocking: %s", e,
                     exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return object_to_dict(result)


@router.post(
    "/tools/execute_bulk",
    summary="Execute multiple tools in one call"
)
def execute_tools_bulk(request: BulkExecuteRequest):
    registry = get_global_registry()
    results = []

    for req in request.requests:
        if req.tool_name not in registry:
            raise HTTPException(status_code=404,
                                detail=f"Tool '{req.tool_name}' not found")

        try:
            res = execute_tool(
                tool_name=req.tool_name,
                input_args=req.input_args,
                repo_url=req.repo_url,
                repo_name=req.repo_name,
                repo_owner=req.repo_owner,
                metadata=req.metadata or {},
                turn_id=req.turn_id,
            )
            results.append({
                "status": "ok",
                "result": object_to_dict(res),
            })
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Unhandled exception in /tools/execute_bulk for %s: %s",
                req.tool_name, e, exc_info=True
            )
            raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "ok",
        "data": results,
    }
