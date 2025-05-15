# modules/agents_running.py

import threading
from typing import Optional, Tuple, List, Dict

from shared.config import config
from modules.db_agents import (
    list_running_agents            as db_list_running_agents,
    add_running_agent              as db_add_running_agent,
    remove_running_agent           as db_remove_running_agent,
    load_current_agent_pointer     as db_load_current_agent_pointer,
    save_current_agent_pointer     as db_save_current_agent_pointer,
    delete_current_agent_pointer   as db_delete_current_agent_pointer,
)
from modules.agent_context import (
    set_current_agent   as _ctx_set_current_agent,
    get_current_agent   as _ctx_get_current_agent,
)
from modules.turns_list import delete_turns_list

# Reentrant lock for our in-memory stack
_current_agent_lock = threading.RLock()
_current_agent: Optional[Tuple[str, str, str]] = None    # (role, id, repo_url)
_agent_stack: List[Tuple[str, str, str]] = []            # LIFO stack

def _cache_init_current_agent():
    """
    On import: load persisted pointer and seed our in-memory stack.
    """
    global _current_agent
    with _current_agent_lock:
        _current_agent = db_load_current_agent_pointer()
        if _current_agent:
            _agent_stack.append(_current_agent)

# initialize at module load
_cache_init_current_agent()

def get_current_agent_tuple() -> Optional[Tuple[str, str, str]]:
    """
    Check per-request context first, then the global pointer.
    Returns a 3-tuple (agent_role, agent_id, repo_url) or None.
    """
    ctx = _ctx_get_current_agent()
    if ctx and any(ctx):
        return ctx
    return _current_agent

def set_current_agent_tuple(
    agent_role: Optional[str],
    agent_id:   Optional[str],
    repo_url:   Optional[str],
) -> None:
    """
    Push (or clear) the current-agent pointer in request-context,
    persistence, and our in-memory stack.
    """
    # 1) request context
    _ctx_set_current_agent(agent_role, agent_id, repo_url)

    # 2) global persistence + stack
    with _current_agent_lock:
        global _current_agent

        # clearing?
        if not (agent_role and agent_id and repo_url):
            db_delete_current_agent_pointer()
            _agent_stack.clear()
            _current_agent = None
            return

        tup = (agent_role, agent_id, repo_url)
        if _current_agent != tup:
            _agent_stack.append(tup)
            db_save_current_agent_pointer(agent_role, agent_id, repo_url)
        _current_agent = tup

def seed_agent(
    agent_role: str,
    repo_url:   str,
    agent_id:   Optional[str] = None,
) -> str:
    """
    Create (or re-use) an agent under (repo_url). If agent_id is provided,
    we INSERT with that ID; if missing, we auto-generate one.
    Returns the agent_id.
    """
    if agent_id:
        existing = db_list_running_agents(repo_url)
        if not any(
            r["agent_role"] == agent_role and r["agent_id"] == agent_id
            for r in existing
        ):
            db_add_running_agent(agent_role, repo_url, agent_id)
        aid = agent_id
    else:
        new_row = db_add_running_agent(agent_role, repo_url)
        aid     = new_row["agent_id"]

    set_current_agent_tuple(agent_role, aid, repo_url)
    return aid

def add_running_agent(
    agent_role: str,
    repo_url:   str,
    agent_id:   Optional[str] = None,
) -> dict:
    """
    Public API: add a new agent. If agent_id is provided, we INSERT with that ID;
    otherwise a fresh one is generated. Returns the new row dict.
    """
    if agent_id:
        return db_add_running_agent(agent_role, repo_url, agent_id)
    return db_add_running_agent(agent_role, repo_url)

def list_running_agents(
    repo_url: Optional[str] = None,
) -> List[dict]:
    """
    Public API: list all agents for a repo.
    If repo_url is omitted, fall back to current-agent context.
    """
    if repo_url is None:
        tup = get_current_agent_tuple()
        if not tup:
            return []
        repo_url = tup[2]
    return db_list_running_agents(repo_url)

def get_current_running_agent(
    repo_url: Optional[str] = None
) -> dict:
    """
    Return the dict for the current agent, or {} if none.
    """
    if repo_url is None:
        tup = get_current_agent_tuple()
        if not tup:
            return {}
        repo_url = tup[2]

    ca = get_current_agent_tuple()
    if not ca or ca[2] != repo_url:
        return {}

    for a in db_list_running_agents(repo_url):
        if a["agent_role"] == ca[0] and a["agent_id"] == ca[1]:
            return a
    return {}

def set_current_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   str
) -> dict:
    """
    Public API: pick an existing agent as current.
    """
    agents = db_list_running_agents(repo_url)
    if not any(
        a["agent_role"] == agent_role and a["agent_id"] == agent_id
        for a in agents
    ):
        raise RuntimeError(
            f"Agent {agent_role}:{agent_id} not found in repo '{repo_url}'"
        )

    set_current_agent_tuple(agent_role, agent_id, repo_url)
    return {
        "message": (
            f"Current agent set to {agent_role}:{agent_id} "
            f"in repo '{repo_url}'"
        )
    }

def remove_running_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
) -> dict:
    """
    Public API:
      1) Forbid removing any agent that’s currently on the call-stack.
      2) Delete from DB and purge turns.
      3) If it was the current/top, pop the stack and restore.
    """
    target = (agent_role, agent_id, repo_url)

    with _current_agent_lock:
        if target in _agent_stack:
            raise RuntimeError("Cannot remove agent still in call-stack")

    count = db_remove_running_agent(agent_role, agent_id, repo_url)
    delete_turns_list(agent_role, agent_id, repo_url)

    with _current_agent_lock:
        if _agent_stack and _agent_stack[-1] == target:
            _agent_stack.pop()
            if _agent_stack:
                set_current_agent_tuple(*_agent_stack[-1])
            else:
                set_current_agent_tuple(None, None, None)

    if count == 0:
        raise RuntimeError(
            f"No such running agent {agent_role}:{agent_id} in repo '{repo_url}'"
        )

    return {
        "message": (
            f"Removed running agent {agent_role}:{agent_id} "
            f"from repo '{repo_url}'"
        )
    }

def get_agent_stack() -> List[Dict[str, str]]:
    """
    Return a snapshot of the current agent call-stack
    (from bottom to top) as a list of dicts with keys:
    agent_role, agent_id, repo_url.
    """
    with _current_agent_lock:
        return [
            {
                "agent_role": role,
                "agent_id":   aid,
                "repo_url":   repo,
            }
            for role, aid, repo in _agent_stack
        ]
