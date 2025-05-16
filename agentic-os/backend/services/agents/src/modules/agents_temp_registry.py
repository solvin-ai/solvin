# modules/agents_temp_registry.py

"""
Client stub for the remote Agent-Manager registry API.
Defines the AgentRegistryItem model and functions to list, upsert, get, and delete
registry entries by agent_role.
"""

from typing import List, Optional, Any, Union
import requests
from pydantic import BaseModel, field_validator
from shared.config import config
import json


def get_agent_manager_api_url() -> str:
    # Will raise KeyError if the key is missing.
    return config["AGENT_MANAGER_API_URL"]


def get_registry_api_base() -> str:
    return f"{get_agent_manager_api_url().rstrip('/')}/api/agent-roles"


class AgentRegistryItem(BaseModel):
    agent_role:               str
    agent_description:        Optional[str] = ""
    allowed_tools:            Any
    default_developer_prompt: Optional[str] = ""
    # we only expose the API's string model identifier here:
    model_name:               Optional[str] = None
    # numeric primary key (if the API returns it):
    model_id:                 Optional[int] = None
    reasoning_level:          Optional[str] = None
    tool_choice:              Optional[str] = None
    message:                  Optional[str] = None

    @field_validator('allowed_tools', mode='before')
    @classmethod
    def _ensure_list(cls, v):
        if isinstance(v, str):
            v = json.loads(v)
        if not isinstance(v, list):
            raise ValueError(f"allowed_tools must be list, got {type(v).__name__}: {v!r}")
        if not all(isinstance(i, str) for i in v):
            raise ValueError(f"allowed_tools must be list[str], got {v!r}")
        return v

    @field_validator('reasoning_level', mode='before')
    @classmethod
    def _empty_reasoning_to_none(cls, v):
        # normalize empty or all-whitespace strings to None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator('tool_choice', mode='before')
    @classmethod
    def _empty_tool_choice_to_none(cls, v):
        # normalize empty or all-whitespace strings to None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # ----------------------------------------------------------------
    # Compatibility shim so you can treat this model like a dict:
    # ----------------------------------------------------------------
    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key: str):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)


def list_registry() -> List[AgentRegistryItem]:
    """
    Fetch all entries from the remote registry.
    Handles the 'agentTypes' wrapper that the remote API returns.
    """
    resp = requests.get(get_registry_api_base())
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "agentTypes" in data and isinstance(data["agentTypes"], list):
        raw_list = data["agentTypes"]
    elif isinstance(data, list):
        raw_list = data
    else:
        raise ValueError(f"Unexpected registry list response shape: {data}")
    return [AgentRegistryItem.model_validate(item) for item in raw_list]


def upsert_agent_role(
    agent_role: str,
    agent_description: str,
    allowed_tools: Union[List[str], str],
    default_developer_prompt: str,
    *,
    model_name: str = None,
    reasoning_level: str = None,
    tool_choice: str = None
) -> AgentRegistryItem:
    """
    1) POST to upsert the registry entry,
    2) GET the entry by agent_role (unwrapping the response as needed),
    3) Merge in the POST's "message",
    4) Return a validated AgentRegistryItem.
    """
    # ensure allowed_tools is a list
    if isinstance(allowed_tools, str):
        allowed_tools = json.loads(allowed_tools)

    payload = {
        "agent_role":               agent_role,
        "agent_description":        agent_description,
        "allowed_tools":            allowed_tools,
        "default_developer_prompt": default_developer_prompt,
    }
    if model_name is not None:
        payload["model_name"] = model_name
    if reasoning_level:
        payload["reasoning_level"] = reasoning_level
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    post_resp = requests.post(get_registry_api_base(), json=payload)
    post_resp.raise_for_status()
    post_data = post_resp.json()  # e.g. { "message": "Agent role created/updated successfully." }

    # fetch back the upserted entry
    fetch_resp = requests.get(get_registry_api_base(), params={"agent_role": agent_role})
    fetch_resp.raise_for_status()
    entries = fetch_resp.json()
    if isinstance(entries, dict) and "agent" in entries:
        entry = entries["agent"]
    elif isinstance(entries, list) and len(entries) == 1:
        entry = entries[0]
    else:
        raise ValueError(f"Unexpected registry fetch response: {entries}")

    entry["message"] = post_data.get("message")
    return AgentRegistryItem.model_validate(entry)


def delete_agent_role(agent_role: str) -> dict:
    """
    Delete an agent registry entry using the agent_role as the identifier.
    Returns a success message upon deletion.
    If the role does not exist, returns a no-op success.
    """
    url = get_registry_api_base()

    fetch_resp = requests.get(url, params={"agent_role": agent_role})
    if fetch_resp.status_code == 404:
        return {"message": f"Agent role '{agent_role}' not found; nothing to delete."}
    fetch_resp.raise_for_status()

    entries = fetch_resp.json()
    if isinstance(entries, dict) and "agent" in entries:
        entry = entries["agent"]
    elif isinstance(entries, list) and len(entries) == 1:
        entry = entries[0]
    else:
        raise ValueError(f"No unique registry entry for role '{agent_role}': {entries}")

    del_resp = requests.delete(url, params={"agent_role": agent_role})
    del_resp.raise_for_status()
    return {"message": f"Agent role '{agent_role}' deleted successfully."}


def get_agent_role(agent_role: str) -> Optional[AgentRegistryItem]:
    """
    Fetch a single agent registry entry by agent_role.
    Returns an AgentRegistryItem if found, else None.
    """
    resp = requests.get(get_registry_api_base(), params={"agent_role": agent_role})
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "agent" in data:
        entry = data["agent"]
    elif isinstance(data, list) and len(data) == 1:
        entry = data[0]
    elif isinstance(data, list) and len(data) == 0:
        return None
    else:
        return None

    return AgentRegistryItem.model_validate(entry)
