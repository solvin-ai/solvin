# shared/client_agents.py

"""
Client library for interacting with the agents backend.
All operations are scoped to a repository via `repo_url`.
"""

import requests
import json
from typing import Optional, List, Dict, Any

from shared.config import config

SERVICE_URL_AGENTS = config["SERVICE_URL_AGENTS"].rstrip("/")
API_VERSION        = "v1"
API_PREFIX         = f"/api/{API_VERSION}"
BASE               = f"{SERVICE_URL_AGENTS}/{API_PREFIX}"
HEADERS            = {"Content-Type": "application/json"}


# ------------ AGENTS REGISTRY ------------

def list_registry() -> List[Dict[str, Any]]:
    """GET /agents/registry/list → data:list"""
    resp = requests.get(f"{BASE}/agents/registry/list", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def get_agent_role(agent_role: str) -> Dict[str, Any]:
    """GET /agents/registry/get?agent_role=… → data:dict"""
    resp = requests.get(
        f"{BASE}/agents/registry/get",
        params={"agent_role": agent_role},
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def upsert_agent_role(
    role: str,
    description: str,
    tools: Any,
    prompt: str,
    model_id: Optional[str] = None,
    model: Optional[str] = None,
    reasoning_level: Optional[str] = None,
    tool_choice: Optional[str] = None
) -> Dict[str, Any]:
    """POST /agents/registry/upsert → data:dict"""
    if isinstance(tools, str):
        tools = json.loads(tools)
    payload: Dict[str, Any] = {
        "agent_role":               role,
        "agent_description":        description,
        "allowed_tools":            tools,
        "default_developer_prompt": prompt,
    }
    if model_id:
        payload["model_id"] = model_id
    if model:
        payload["model"] = model
    if reasoning_level:
        payload["reasoning_level"] = reasoning_level
    if tool_choice:
        payload["tool_choice"] = tool_choice

    resp = requests.post(
        f"{BASE}/agents/registry/upsert",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def delete_agent_role(agent_role: str) -> Dict[str, Any]:
    """DELETE /agents/registry/delete?agent_role=… → data:dict"""
    resp = requests.delete(
        f"{BASE}/agents/registry/delete",
        params={"agent_role": agent_role},
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


# ------------ AGENTS RUNNING ------------

def list_running_agents(repo_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """GET /agents/running/list?repo_url=… → data:list"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    resp = requests.get(
        f"{BASE}/agents/running/list",
        params={"repo_url": repo_url},
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def get_current_running_agent(repo_url: Optional[str] = None) -> Dict[str, Any]:
    """GET /agents/running/current?repo_url=… → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    resp = requests.get(
        f"{BASE}/agents/running/current",
        params={"repo_url": repo_url},
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def add_running_agent(
    agent_role: str,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """POST /agents/running/add {agent_role,repo_url} → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    payload = {"agent_role": agent_role, "repo_url": repo_url}
    resp = requests.post(
        f"{BASE}/agents/running/add",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def remove_running_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """POST /agents/running/remove {agent_role,agent_id,repo_url} → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    payload = {"agent_role": agent_role, "agent_id": agent_id, "repo_url": repo_url}
    resp = requests.post(
        f"{BASE}/agents/running/remove",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def set_current_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """POST /agents/running/set_current {agent_role,agent_id,repo_url} → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    payload = {"agent_role": agent_role, "agent_id": agent_id, "repo_url": repo_url}
    resp = requests.post(
        f"{BASE}/agents/running/set_current",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def clear_repo(repo_url: Optional[str] = None) -> Dict[str, Any]:
    """DELETE /agents/clear_repo?repo_url=… → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    resp = requests.delete(
        f"{BASE}/agents/clear_repo",
        params={"repo_url": repo_url},
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def get_agent_stack() -> List[Dict[str, Any]]:
    """GET /agents/running/stack → data:list"""
    resp = requests.get(
        f"{BASE}/agents/running/stack",
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


# ------------ MESSAGES (CRUD & Filters) ------------

def add_message(
    agent_role: str,
    agent_id:   str,
    role:       str,
    content:    str,
    repo_url:   Optional[str] = None,
    **extra_fields
) -> Dict[str, Any]:
    """POST /messages/add → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    payload = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "role":       role,
        "content":    content,
        "repo_url":   repo_url
    }
    payload.update(extra_fields)
    resp = requests.post(
        f"{BASE}/messages/add",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def list_messages(
    agent_role: str,
    agent_id:   str,
    repo_url:   Optional[str] = None,
    role:       Optional[str] = None,
    turn_id:    Optional[int] = None,
) -> List[Dict[str, Any]]:
    """GET /messages/list?agent_role=…&agent_id=…&repo_url=…[&role=…][&turn_id=…] → data:list"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    params: Dict[str, Any] = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "repo_url":   repo_url
    }
    if role is not None:
        params["role"] = role
    if turn_id is not None:
        params["turn_id"] = turn_id

    resp = requests.get(
        f"{BASE}/messages/list",
        params=params,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def get_message(
    agent_role: str,
    agent_id:   str,
    message_id: int,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """GET /messages/get?agent_role=…&agent_id=…&message_id=…&repo_url=… → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    params = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "message_id": message_id,
        "repo_url":   repo_url
    }
    resp = requests.get(
        f"{BASE}/messages/get",
        params=params,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def remove_message(
    agent_role: str,
    agent_id:   str,
    message_id: int,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """DELETE /messages/remove?agent_role=…&agent_id=…&message_id=…&repo_url=… → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    params = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "message_id": message_id,
        "repo_url":   repo_url
    }
    resp = requests.delete(
        f"{BASE}/messages/remove",
        params=params,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def remove_all_messages(
    agent_role: str,
    agent_id:   str,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """DELETE /messages/remove_all?agent_role=…&agent_id=…&repo_url=… → data:dict"""
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    params = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "repo_url":   repo_url
    }
    resp = requests.delete(
        f"{BASE}/messages/remove_all",
        params=params,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def clear_history(
    repo_url:   Optional[str] = None,
    agent_role: Optional[str] = None,
    agent_id:   Optional[str] = None,
) -> Dict[str, Any]:
    """
    DELETE /messages/clear?repo_url=&agent_role=&agent_id=
    Clear turns & messages (and reset counters) matching the filters.
    '*' is used when any of repo_url, agent_role or agent_id is None.
    """
    params = {
        "repo_url":   repo_url   or "*",
        "agent_role": agent_role or "*",
        "agent_id":   agent_id   or "*",
    }
    resp = requests.delete(
        f"{BASE}/messages/clear",
        params=params,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


# ------------ TURNS (list & get) ------------

def list_turns(
    agent_role: str,
    agent_id:   str,
    repo_url:   Optional[str] = None,
    limit:      int            = 50,
    offset:     int            = 0,
    status:     Optional[str]  = None,
    toolName:   Optional[str]  = None,
    deleted:    Optional[bool] = None,
    startTime:  Optional[str]  = None,
    endTime:    Optional[str]  = None,
    sort:       Optional[str]  = None
) -> Dict[str, Any]:
    """
    GET /turns/list?agent_role=…&agent_id=…&repo_url=… plus
        filter.status, filter.toolName, filter.deleted, filter.startTime,
        filter.endTime, sort, limit, offset
    → data:{turns:list, totalContextKb:float}
    """
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    params: Dict[str, Any] = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "repo_url":   repo_url,
        "limit":      limit,
        "offset":     offset,
    }
    if status   is not None: params["filter.status"]    = status
    if toolName is not None: params["filter.toolName"]  = toolName
    if deleted  is not None: params["filter.deleted"]   = str(deleted).lower()
    if startTime:            params["filter.startTime"] = startTime
    if endTime:              params["filter.endTime"]   = endTime
    if sort:                 params["sort"]            = sort

    resp = requests.get(f"{BASE}/turns/list", params=params, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def get_turn(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
    turn:       int
) -> Dict[str, Any]:
    """GET /turns/get?agent_role=…&agent_id=…&repo_url=…&turn=… → data:dict"""
    params = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "repo_url":   repo_url,
        "turn":       turn,
    }
    resp = requests.get(f"{BASE}/turns/get", params=params, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


# ------------ RUN-TO-COMPLETION & SINGLE-TURN ------------

def run_to_completion(
    agent_role:  str,
    user_prompt: str,
    agent_id:    Optional[str] = None,
    repo_url:    Optional[str] = None
) -> Dict[str, Any]:
    """
    POST /messages/run_to_completion
      {agent_role, [agent_id], [repo_url], [user_prompt]}
    → data:{agent_id, status, total_time, response}
    """
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    payload: Dict[str, Any] = {"agent_role": agent_role}
    if agent_id is not None:
        payload["agent_id"] = agent_id
    payload["repo_url"] = repo_url
    if user_prompt:
        payload["user_prompt"] = user_prompt

    resp = requests.post(
        f"{BASE}/messages/run_to_completion",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def submit_to_llm(
    agent_role: str,
    agent_id:   str,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """
    POST /messages/submit_to_llm
      {agent_role, agent_id, [repo_url]}
    → data:{turn_meta, messages}
    """
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    payload: Dict[str, Any] = {"agent_role": agent_role, "agent_id": agent_id, "repo_url": repo_url}
    resp = requests.post(
        f"{BASE}/messages/submit_to_llm",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def broadcast_to_agents(
    agent_roles: List[str],
    messages:    Any,
    repo_url:    Optional[str] = None,
    **extra_fields
) -> Dict[str, Any]:
    """
    POST /messages/broadcast
      {agent_roles:[…], messages:…, repo_url:…, ...}
    → data:{success_count, errors}
    """
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    payload: Dict[str, Any] = {
        "agent_roles": agent_roles,
        "messages":    messages,
        "repo_url":    repo_url
    }
    payload.update(extra_fields)

    resp = requests.post(
        f"{BASE}/messages/broadcast",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


# ------------ SERVICE HEALTH & STATUS ------------

def health() -> Dict[str, Any]:
    """GET /health → data:dict"""
    resp = requests.get(f"{BASE}/health", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def status() -> Dict[str, Any]:
    """GET /status → data:dict"""
    resp = requests.get(f"{BASE}/status", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def ready() -> Dict[str, Any]:
    """GET /ready → data:dict"""
    resp = requests.get(f"{BASE}/ready", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]
