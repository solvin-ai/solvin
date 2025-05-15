# routers/router_tools.py

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, List, Any

from shared.logger import logger
from service_tools import global_registry
from modules.routers_utils import object_to_dict

router = APIRouter(tags=["Tools"])


@router.get("/tools/list", summary="List all tools")
def tools_list():
    """
    GET /tools/list
    Returns RPC envelope: { status, data: [ {tool_name}, … ], error }
    """
    try:
        data = [{"tool_name": name} for name in global_registry.keys()]
        return {"status": "ok", "data": data, "error": None}
    except Exception as e:
        logger.error("Unhandled exception in /tools/list: %s", e, exc_info=True)
        return {
            "status": "error",
            "data": None,
            "error": {"code": None, "message": str(e)},
        }


@router.api_route(
    "/tools/info",
    methods=["GET", "POST"],
    summary="Get tool metadata & schema"
)
def tools_info(
    tool_name: Optional[str] = Query(None, description="Single tool name"),
    meta: bool = Query(True, description="Include metadata"),
    schema: bool = Query(True, description="Include schema"),
    body: Optional[dict] = Body(None),
):
    """
    GET or POST /tools/info
    Returns RPC envelope: { status, data, error }
      - data is a dict (single‐tool info or mapping of tool→info) on status=="ok"
      - for single‐tool, missing → status="error", code="TOOL_NOT_FOUND"
    """
    try:
        # 1) Determine requested tool name(s)
        names: List[str] = []
        if body:
            if "tool_names" in body:
                names = body["tool_names"]
                if not isinstance(names, list):
                    raise HTTPException(status_code=400, detail="tool_names must be a list")
            elif "tool_name" in body:
                names = [body["tool_name"]]
            meta = bool(body.get("meta", meta))
            schema = bool(body.get("schema", schema))
        elif tool_name:
            names = [tool_name]

        if not names:
            raise HTTPException(status_code=400, detail="No tool_name(s) specified")

        # 2) Build info dict(s)
        result: Dict[str, Any] = {}
        for name in names:
            tool = global_registry.get(name)
            if tool:
                info: Dict[str, Any] = {}
                if meta:
                    info.update({k: v for k, v in tool.items() if k != "schema"})
                if schema:
                    info["schema"] = tool.get("schema", {})
                result[name] = object_to_dict(info)
            else:
                result[name] = None

        # 3) Single‐tool unwrap + not‐found → RPC error
        if len(names) == 1:
            single = names[0]
            if result[single] is None:
                return {
                    "status": "error",
                    "data": None,
                    "error": {
                        "code": "TOOL_NOT_FOUND",
                        "message": f"Tool '{single}' not found",
                    },
                }
            data = result[single]
        else:
            data = result

        return {"status": "ok", "data": data, "error": None}

    except HTTPException as he:
        msg = he.detail if isinstance(he.detail, str) else str(he.detail)
        logger.warning("Tools info HTTPException: %s", msg)
        return {"status": "error", "data": None, "error": {"code": None, "message": msg}}

    except Exception as e:
        logger.error("Unhandled exception in /tools/info: %s", e, exc_info=True)
        return {"status": "error", "data": None, "error": {"code": None, "message": str(e)}}