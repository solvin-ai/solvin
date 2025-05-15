# shared/client_tools.py

import requests
from typing import Any, Dict, List, Optional

from shared.config import config
from shared.logger import logger

# HTTP-based service endpoints
SERVICE_URL   = config["SERVICE_URL_TOOLS"].rstrip("/")
API_VERSION   = "v1"
BASE_HTTP     = f"{SERVICE_URL}/api/{API_VERSION}"
HEADERS_HTTP  = {"Content-Type": "application/json"}


class ToolError(Exception):
    """
    Raised when the tools service returns status="error" in its RPC envelope.
    """
    def __init__(self, code: Optional[str], message: str):
        super().__init__(f"[{code}] {message}")
        self.code    = code
        self.message = message


def _unwrap(resp: requests.Response) -> Any:
    """
    1) Raise for HTTP-level errors.
    2) Parse JSON envelope.
    3) If status=="error", raise ToolError.
    4) Otherwise return env["data"].
    """
    resp.raise_for_status()
    try:
        env = resp.json()
    except ValueError as e:
        logger.error("Invalid JSON response from %s: %s", resp.url, e)
        raise ToolError(None, "Invalid JSON response")

    status = env.get("status")
    if status == "error":
        err = env.get("error") or {}
        raise ToolError(err.get("code"), err.get("message", "<no message>"))

    return env.get("data")


def health() -> Dict[str, Any]:
    """
    GET /api/v1/health
    Returns: {"status":"ok"}
    """
    url = f"{BASE_HTTP}/health"
    resp = requests.get(url, headers=HEADERS_HTTP)
    return _unwrap(resp)


def ready() -> Dict[str, Any]:
    """
    GET /api/v1/ready
    Returns: {"status":"ready"}
    """
    url = f"{BASE_HTTP}/ready"
    resp = requests.get(url, headers=HEADERS_HTTP)
    return _unwrap(resp)


def status() -> Dict[str, Any]:
    """
    GET /api/v1/status
    Returns: {"status", "requests", "version", "uptime_seconds", "tool_count"}
    """
    url = f"{BASE_HTTP}/status"
    resp = requests.get(url, headers=HEADERS_HTTP)
    return _unwrap(resp)


def tools_list() -> List[Dict[str, Any]]:
    """
    GET /api/v1/tools/list
    Returns: list of {"tool_name": ...}
    """
    url = f"{BASE_HTTP}/tools/list"
    resp = requests.get(url, headers=HEADERS_HTTP)
    return _unwrap(resp)


def tools_info(
    *,
    tool_name: Optional[str] = None,
    tool_names: Optional[List[str]] = None,
    meta: bool = True,
    schema: bool = True
) -> Any:
    """
    GET or POST /api/v1/tools/info
    - Single: GET  with ?tool_name=foo&meta=...&schema=...
    - Bulk:   POST with json={"tool_names": [...]} plus same flags
    """
    url = f"{BASE_HTTP}/tools/info"
    params = {"meta": meta, "schema": schema}

    if tool_name:
        params["tool_name"] = tool_name
        resp = requests.get(url, params=params, headers=HEADERS_HTTP)
    elif tool_names:
        resp = requests.post(
            url,
            params=params,
            json={"tool_names": tool_names},
            headers=HEADERS_HTTP
        )
    else:
        raise ValueError("Either tool_name or tool_names must be provided")

    return _unwrap(resp)


def execute_tool(
    tool_name: str,
    input_args: Dict[str, Any],
    repo_url: str,
    repo_name: str,
    repo_owner: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    turn_id: Optional[str] = None,
    reply_to: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fire-and-forget: enqueue a tool execution via HTTP /tools/execute.
    Optionally include a `reply_to` inbox for per-request responses.
    Returns: {"stream": "<stream>", "seq": <seq>}
    """
    url = f"{BASE_HTTP}/tools/execute"
    payload: Dict[str, Any] = {
        "tool_name":  tool_name,
        "input_args": input_args or {},
        "repo_url":   repo_url,
        "repo_name":  repo_name,
    }
    if repo_owner is not None:
        payload["repo_owner"] = repo_owner
    if metadata is not None:
        payload["metadata"] = metadata
    if turn_id is not None:
        payload["turn_id"] = turn_id
    if reply_to is not None:
        payload["reply_to"] = reply_to

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=HEADERS_HTTP,
            timeout=config.get("HTTP_TIMEOUT", 30),
        )
    except Exception as e:
        logger.error("HTTP POST %s failed: %s", url, e, exc_info=True)
        raise

    return _unwrap(resp)


def execute_tool_blocking(
    tool_name: str,
    input_args: Dict[str, Any],
    repo_url: str,
    repo_name: str,
    repo_owner: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    turn_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Blocking: execute a tool via HTTP /tools/execute-blocking.
    Returns the full tool response envelope, e.g.:
      {
        "status": "ok",
        "response": {...},
        "error": null
      }
    """
    url = f"{BASE_HTTP}/tools/execute-blocking"
    payload: Dict[str, Any] = {
        "tool_name":  tool_name,
        "input_args": input_args or {},
        "repo_url":   repo_url,
        "repo_name":  repo_name,
    }
    if repo_owner is not None:
        payload["repo_owner"] = repo_owner
    if metadata is not None:
        payload["metadata"] = metadata
    if turn_id is not None:
        payload["turn_id"] = turn_id

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=HEADERS_HTTP,
            timeout=config.get("HTTP_TIMEOUT", 60),
        )
    except Exception as e:
        logger.error("HTTP POST %s failed: %s", url, e, exc_info=True)
        raise

    return _unwrap(resp)


def execute_bulk(
    requests_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Bulk fire-and-forget via HTTP /tools/execute_bulk.
    Returns list of {"stream": ..., "seq": ...}
    """
    url = f"{BASE_HTTP}/tools/execute_bulk"
    payload = {"requests": requests_list}

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=HEADERS_HTTP,
            timeout=config.get("HTTP_TIMEOUT", 60),
        )
    except Exception as e:
        logger.error("HTTP POST %s failed: %s", url, e, exc_info=True)
        raise

    return _unwrap(resp)
