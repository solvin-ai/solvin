# routers/router_execute.py

import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.logger import logger
from shared.config import config

from modules.tools_jetstream_pub import publish_exec_request
from modules.tools_executor import execute_tool
from modules.tools_registry import get_global_registry
from modules.routers_utils import object_to_dict

router = APIRouter(tags=["Tools"])


class ExecuteRequest(BaseModel):
    tool_name: str
    input_args: Dict[str, Any]
    repo_name: str
    repo_owner: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}
    turn_id: Optional[str] = None
    reply_to: Optional[str] = None   # ← allow per-request inbox


class BulkExecuteRequest(BaseModel):
    requests: List[ExecuteRequest]


@router.post(
    "/tools/execute",
    summary="Publish a tool execution request to JetStream (non-blocking)"
)
async def execute_tool_nonblocking(request: ExecuteRequest):
    registry = get_global_registry()
    if request.tool_name not in registry:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found")

    try:
        ack = await publish_exec_request(request.dict())
    except Exception as e:
        logger.error("Failed to enqueue execution request: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to enqueue execution request")

    return {
        "status": "ok",
        "data": {
            "stream": ack.stream,
            "seq": ack.seq,
        }
    }


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
            repo_name=request.repo_name,
            repo_owner=request.repo_owner,
            metadata=request.metadata or {},
            turn_id=request.turn_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unhandled exception in /tools/execute-blocking: %s", e, exc_info=True)
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
            raise HTTPException(status_code=404, detail=f"Tool '{req.tool_name}' not found")

        try:
            res = execute_tool(
                tool_name=req.tool_name,
                input_args=req.input_args,
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
