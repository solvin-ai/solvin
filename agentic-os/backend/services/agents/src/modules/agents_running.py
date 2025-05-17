# modules/agents_running.py

import threading
from typing import Optional, Tuple, List, Dict, Any

from modules.db_agents import (
    list_running_agents    as db_list_running_agents,
    add_running_agent      as db_add_running_agent,
    remove_running_agent   as db_remove_running_agent,
)

# ─── Thread‐local context ─────────────────────────────────────────────────────

_thread_ctx = threading.local()

def _ensure_thread_ctx():
    if not hasattr(_thread_ctx, "agent_stack"):
        _thread_ctx.agent_stack = []                # type: List[Tuple[str,str,str]]
    if not hasattr(_thread_ctx, "current_agent"):
        _thread_ctx.current_agent = None            # type: Optional[Tuple[str,str,str]]

def get_current_agent_tuple() -> Optional[Tuple[str, str, str]]:
    """
    Return (agent_role, agent_id, repo_url) for this thread, or None.
    """
    _ensure_thread_ctx()
    return _thread_ctx.current_agent    # type: ignore

def set_thread_current_agent_tuple(
    agent_role: Optional[str],
    agent_id:   Optional[str],
    repo_url:   Optional[str],
) -> None:
    """
    Update only the thread-local 'current_agent' pointer (and stack).
    Does NOT touch the DB.
    """
    _ensure_thread_ctx()
    if agent_role and agent_id and repo_url:
        tup = (agent_role, agent_id, repo_url)
        _thread_ctx.agent_stack.append(tup)
        _thread_ctx.current_agent = tup    # type: ignore
    else:
        _thread_ctx.agent_stack = []
        _thread_ctx.current_agent = None   # type: ignore


# ─── Agent‐seeding logic ─────────────────────────────────────────────────────

def seed_agent(
    agent_role: str,
    repo_url:   str,
    agent_id:   str,
) -> str:
    """
    Create (or reuse) exactly one agent row for (agent_role, repo_url).

    Must be called with a non‐empty agent_id (MD5 computed upstream).
    Never uses any DB‐generated sequential IDs.
    Always sets the thread‐local current_agent pointer.
    """
    if not agent_id or not agent_id.strip():
        raise ValueError(
            f"seed_agent: agent_id is required and must be non-empty "
            f"(role={agent_role}, repo_url={repo_url})"
        )
    aid = agent_id.strip()

    # insert into DB only if missing
    existing = db_list_running_agents(repo_url)
    if not any(r["agent_role"] == agent_role and r["agent_id"] == aid for r in existing):
        db_add_running_agent(agent_role, repo_url, aid)

    # update only the thread-local pointer
    set_thread_current_agent_tuple(agent_role, aid, repo_url)
    return aid

def pop_current_agent() -> None:
    """
    Remove the most‐recently pushed agent from this thread’s context,
    restoring its parent (or None).
    """
    _ensure_thread_ctx()
    if _thread_ctx.agent_stack:
        _thread_ctx.agent_stack.pop()
    if _thread_ctx.agent_stack:
        _thread_ctx.current_agent = _thread_ctx.agent_stack[-1]
    else:
        _thread_ctx.current_agent = None


# ─── Other public agent-management APIs ─────────────────────────────────────

def add_running_agent(
    agent_role: str,
    repo_url:   str,
    agent_id:   Optional[str] = None,
) -> Dict[str, Any]:
    """
    Insert a new agent (for manual/UI use).
    """
    return db_add_running_agent(agent_role, repo_url, agent_id)

def list_running_agents(
    repo_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List all agents in this repo (or if repo_url is None, in the
    current thread’s repo).
    """
    if repo_url is None:
        cur = get_current_agent_tuple()
        if not cur:
            return []
        repo_url = cur[2]
    return db_list_running_agents(repo_url)

def get_current_running_agent(
    repo_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return the single agent row matching this thread’s current pointer.
    """
    cur = get_current_agent_tuple()
    if not cur:
        return {}
    role, aid, rurl = cur
    if repo_url and rurl != repo_url:
        return {}
    for a in db_list_running_agents(rurl):
        if a["agent_role"] == role and a["agent_id"] == aid:
            return a
    return {}

def set_current_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
) -> Dict[str, Any]:
    """
    Make (role,agent_id,repo_url) the thread-local current.
    Must already exist in the DB.
    """
    if not any(
        a["agent_role"] == agent_role and a["agent_id"] == agent_id
        for a in db_list_running_agents(repo_url)
    ):
        raise RuntimeError(f"Agent {agent_role}:{agent_id} not found in repo '{repo_url}'")

    set_thread_current_agent_tuple(agent_role, agent_id, repo_url)
    return {
        "message": f"Current agent set to {agent_role}:{agent_id} in repo '{repo_url}'"
    }

def remove_running_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
) -> Dict[str, Any]:
    """
    1) Forbid deleting any agent still in this thread’s call-stack.
    2) Delete from DB and purge its turn history.
    3) If it was current, pop back to the parent.
    """
    _ensure_thread_ctx()
    target = (agent_role, agent_id, repo_url)

    # cannot delete an in-flight/current agent
    if target in _thread_ctx.agent_stack:
        raise RuntimeError("Cannot remove agent still in call-stack")

    # delete from DB
    count = db_remove_running_agent(agent_role, agent_id, repo_url)

    # delete its turn history
    from modules.turns_list import delete_turns_list  # lazy import
    delete_turns_list(agent_role, agent_id, repo_url)

    # restore previous if it was current
    stack = _thread_ctx.agent_stack
    if stack and stack[-1] == target:
        stack.pop()
        if stack:
            set_thread_current_agent_tuple(*stack[-1])
        else:
            set_thread_current_agent_tuple(None, None, None)

    if count == 0:
        raise RuntimeError(f"No such running agent {agent_role}:{agent_id} in repo '{repo_url}'")

    return {
        "message": f"Removed running agent {agent_role}:{agent_id} from repo '{repo_url}'"
    }

def get_agent_stack() -> List[Dict[str, str]]:
    """
    Return this thread’s agent-call stack (bottom→top),
    including parent linkage.
    """
    _ensure_thread_ctx()
    out: List[Dict[str, str]] = []
    for idx, (role, aid, repo) in enumerate(_thread_ctx.agent_stack):
        rec: Dict[str, str] = {
            "agent_role": role,
            "agent_id":   aid,
            "repo_url":   repo,
        }
        if idx > 0:
            pr, pa, _ = _thread_ctx.agent_stack[idx - 1]
            rec["parent_role"] = pr
            rec["parent_id"]   = pa
        else:
            rec["parent_role"] = ""
            rec["parent_id"]   = ""
        out.append(rec)
    return out
