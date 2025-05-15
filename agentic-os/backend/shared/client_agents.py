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
    resp = requests.get(f"{BASE}/agents/registry/list", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def get_agent_role(agent_role: str) -> Dict[str, Any]:
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
    resp = requests.delete(
        f"{BASE}/agents/registry/delete",
        params={"agent_role": agent_role},
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


# ------------ AGENTS RUNNING ------------

def add_running_agent(
    agent_role: str,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new agent instance on the Agents service.
    """
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    if not repo_url:
        raise ValueError("add_running_agent: repo_url is required")

    payload = {
        "agent_role": agent_role,
        "repo_url":   repo_url,
    }
    resp = requests.post(
        f"{BASE}/agents/running/add",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def list_running_agents(
    repo_url: Optional[str] = None
) -> List[Dict[str, Any]]:
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    if not repo_url:
        raise ValueError("list_running_agents: repo_url is required")

    resp = requests.get(
        f"{BASE}/agents/running/list",
        params={"repo_url": repo_url},
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def get_current_running_agent(
    repo_url: Optional[str] = None
) -> Dict[str, Any]:
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    if not repo_url:
        raise ValueError("get_current_running_agent: repo_url is required")

    resp = requests.get(
        f"{BASE}/agents/running/current",
        params={"repo_url": repo_url},
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def set_current_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    if not repo_url:
        raise ValueError("set_current_agent: repo_url is required")

    payload = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "repo_url":   repo_url
    }
    resp = requests.post(
        f"{BASE}/agents/running/set_current",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]


def get_agent_stack(
    repo_url: Optional[str] = None
) -> List[Dict[str, Any]]:
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    params: Dict[str, Any] = {}
    if repo_url:
        params["repo_url"] = repo_url

    resp = requests.get(
        f"{BASE}/agents/running/stack",
        params=params or None,
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


def broadcast_to_agents(
    agent_roles: List[str],
    messages:    Any,
    repo_url:    Optional[str] = None,
    **extra_fields
) -> Dict[str, Any]:
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


# ------------ TURNS (list, get & metadata) ------------

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
    params = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "repo_url":   repo_url,
        "turn":       turn,
    }
    resp = requests.get(f"{BASE}/turns/get", params=params, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def get_turns_metadata(
    agent_role: str,
    agent_id:   str,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch the per-conversation metadata dict.
      GET /turns/metadata?agent_role=…&agent_id=…&repo_url=…
    """
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    if not repo_url:
        raise ValueError("get_turns_metadata: repo_url is required")

    params = {
        "agent_role": agent_role,
        "agent_id":   agent_id,
        "repo_url":   repo_url,
    }
    resp = requests.get(f"{BASE}/turns/metadata", params=params, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


# ------------ RUN-AGENT-TASK (via run_agent_task) ------------

def run_agent_task(
    agent_role:  str,
    repo_url:    str,
    user_prompt: str,
    agent_id:    Optional[str] = None
) -> Dict[str, Any]:
    """
    Sends the prompt to the Agents-service’s run_agent_task endpoint,
    which will find-or-create the agent, set it current, and drive it to completion.
    """
    if not repo_url:
        raise ValueError("run_agent_task: repo_url is required")

    payload: Dict[str, Any] = {
        "agent_role":  agent_role,
        "repo_url":    repo_url,
        "user_prompt": user_prompt,
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id

    resp = requests.post(
        f"{BASE}/llm/run_agent_task",
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
    if repo_url is None:
        repo_url = config.get("REPO_URL", "")
    payload = {"agent_role": agent_role, "agent_id": agent_id, "repo_url": repo_url}

    resp = requests.post(
        f"{BASE}/messages/submit_to_llm",
        json=payload,
        headers=HEADERS
    )
    resp.raise_for_status()
    return resp.json()["data"]

# ------------ SERVICE HEALTH & STATUS ------------

def health() -> Dict[str, Any]:
    resp = requests.get(f"{BASE}/health", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def status() -> Dict[str, Any]:
    resp = requests.get(f"{BASE}/status", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]


def ready() -> Dict[str, Any]:
    resp = requests.get(f"{BASE}/ready", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]
