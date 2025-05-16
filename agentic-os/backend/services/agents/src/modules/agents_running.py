# modules/agents_running.py

import threading
from typing import Optional, Tuple, List, Dict
import hashlib

from shared.config import config
from modules.db_agents import (
    list_running_agents           as db_list_running_agents,
    add_running_agent             as db_add_running_agent,
    remove_running_agent          as db_remove_running_agent,
    load_current_agent_pointer    as db_load_current_agent_pointer,
    save_current_agent_pointer    as db_save_current_agent_pointer,
    delete_current_agent_pointer  as db_delete_current_agent_pointer,
)

# ─── Thread-local context ─────────────────────────────────────────────────────

_thread_ctx = threading.local()

def _ensure_thread_ctx():
    """
    Ensure this thread has `.current_agent` and `.agent_stack`.
    On first use, load the persisted pointer into this thread.
    """
    if not hasattr(_thread_ctx, "agent_stack"):
        _thread_ctx.agent_stack = []  # type: List[Tuple[str,str,str]]
    if not hasattr(_thread_ctx, "current_agent"):
        ptr = db_load_current_agent_pointer()  # either (role,id,repo) or None
        _thread_ctx.current_agent = ptr  # type: ignore
        if ptr:
            _thread_ctx.agent_stack.append(ptr)  # seed the stack

# ─── Public API: get/set the “current agent” ─────────────────────────────────

def get_current_agent_tuple() -> Optional[Tuple[str, str, str]]:
    """
    Return (agent_role, agent_id, repo_url) for *this thread*, or None.
    """
    _ensure_thread_ctx()
    return _thread_ctx.current_agent  # type: ignore

def set_current_agent_tuple(
    agent_role: Optional[str],
    agent_id:   Optional[str],
    repo_url:   Optional[str],
) -> None:
    """
    Mark the current agent in this thread (and persist it).
    If any argument is falsy, clears both thread-local and persisted pointer.
    """
    _ensure_thread_ctx()

    # clear?
    if not (agent_role and agent_id and repo_url):
        db_delete_current_agent_pointer()
        _thread_ctx.agent_stack = []
        _thread_ctx.current_agent = None  # type: ignore
        return

    tup = (agent_role, agent_id, repo_url)
    # only push if different from last
    if _thread_ctx.current_agent != tup:
        _thread_ctx.agent_stack.append(tup)
        db_save_current_agent_pointer(agent_role, agent_id, repo_url)
    _thread_ctx.current_agent = tup  # type: ignore

# ─── Agent seeding logic ─────────────────────────────────────────────────────

def _derive_id_from_prompt(prompt: str) -> str:
    return hashlib.md5(prompt.encode("utf-8")).hexdigest()

def seed_agent(
    agent_role:  str,
    repo_url:    str,
    agent_id:    Optional[str] = None,
    user_prompt: Optional[str] = None,
) -> str:
    """
    Ensure exactly one agent per (role,repo):
      1) Require a non-empty user_prompt for all roles.
      2) If DB already has one for this role/repo, reuse it.
      3) Otherwise pick a new ID (explicit or MD5-of-prompt), insert, and persist current.
    Returns the agent_id.
    """
    # 1) enforce prompt
    assert user_prompt and user_prompt.strip(), (
        f"seed_agent: must supply non-empty user_prompt for role={agent_role}"
    )

    # 2) check DB for existing agent of this role/repo
    rows = db_list_running_agents(repo_url)
    for r in rows:
        if r["agent_role"] == agent_role:
            aid = r["agent_id"]
            set_current_agent_tuple(agent_role, aid, repo_url)
            return aid

    # 3) no existing → pick or derive new ID
    if agent_id:
        chosen = agent_id
    else:
        chosen = _derive_id_from_prompt(user_prompt)

    db_add_running_agent(agent_role, repo_url, chosen)
    set_current_agent_tuple(agent_role, chosen, repo_url)
    return chosen

# ─── Other public agent‐management APIs ──────────────────────────────────────

def add_running_agent(
    agent_role: str,
    repo_url:   str,
    agent_id:   Optional[str] = None,
) -> dict:
    if agent_id:
        return db_add_running_agent(agent_role, repo_url, agent_id)
    return db_add_running_agent(agent_role, repo_url)

def list_running_agents(
    repo_url: Optional[str] = None,
) -> List[dict]:
    if repo_url is None:
        cur = get_current_agent_tuple()
        if not cur:
            return []
        repo_url = cur[2]
    return db_list_running_agents(repo_url)

def get_current_running_agent(
    repo_url: Optional[str] = None,
) -> dict:
    if repo_url is None:
        cur = get_current_agent_tuple()
        if not cur:
            return {}
        repo_url = cur[2]

    cur = get_current_agent_tuple()
    if not cur or cur[2] != repo_url:
        return {}

    for a in db_list_running_agents(repo_url):
        if a["agent_role"] == cur[0] and a["agent_id"] == cur[1]:
            return a
    return {}

def set_current_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
) -> dict:
    agents = db_list_running_agents(repo_url)
    if not any(a["agent_role"] == agent_role and a["agent_id"] == agent_id for a in agents):
        raise RuntimeError(f"Agent {agent_role}:{agent_id} not found in repo '{repo_url}'")
    set_current_agent_tuple(agent_role, agent_id, repo_url)
    return {
        "message": f"Current agent set to {agent_role}:{agent_id} in repo '{repo_url}'"
    }

def remove_running_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
) -> dict:
    """
    1) Forbid deleting any agent still in *this thread’s* stack.
    2) Delete from DB + purge turns.
    3) Pop the stack if it was on top, restoring the parent pointer.
    """
    target = (agent_role, agent_id, repo_url)
    _ensure_thread_ctx()

    # cannot delete in‐flight agent
    if target in _thread_ctx.agent_stack:
        raise RuntimeError("Cannot remove agent still in call-stack")

    count = db_remove_running_agent(agent_role, agent_id, repo_url)
    from modules.turns_list import delete_turns_list
    delete_turns_list(agent_role, agent_id, repo_url)

    # pop & restore if it was on top
    stack = _thread_ctx.agent_stack
    if stack and stack[-1] == target:
        stack.pop()
        if stack:
            set_current_agent_tuple(*stack[-1])
        else:
            set_current_agent_tuple(None, None, None)

    if count == 0:
        raise RuntimeError(f"No such running agent {agent_role}:{agent_id} in repo '{repo_url}'")

    return {"message": f"Removed running agent {agent_role}:{agent_id} from repo '{repo_url}'"}

def get_agent_stack() -> List[Dict[str, str]]:
    """
    Return this thread’s agent‐call stack (bottom→top), with parent links.
    """
    _ensure_thread_ctx()
    snapshot: List[Dict[str, Optional[str]]] = []
    for idx, (role, aid, repo) in enumerate(_thread_ctx.agent_stack):
        entry: Dict[str, Optional[str]] = {
            "agent_role": role,
            "agent_id":   aid,
            "repo_url":   repo,
        }
        if idx > 0:
            pr, pa, _ = _thread_ctx.agent_stack[idx - 1]
            entry["parent_role"] = pr
            entry["parent_id"]   = pa
        else:
            entry["parent_role"] = None
            entry["parent_id"]   = None
        snapshot.append(entry)  # type: ignore
    return snapshot  # type: ignore
