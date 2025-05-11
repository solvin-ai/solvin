# modules/agents_running.py

import threading
from typing import Optional, Tuple, List, Dict

from shared.config import config
from modules.db_agents import (
    list_running_agents               as db_list_running_agents,
    add_running_agent                 as db_add_running_agent,
    remove_running_agent              as db_remove_running_agent,
    load_current_agent_pointer        as db_load_current_agent_pointer,
    save_current_agent_pointer        as db_save_current_agent_pointer,
    delete_current_agent_pointer      as db_delete_current_agent_pointer,
)
from modules.agent_context import (
    set_current_agent   as _ctx_set_current_agent,
    get_current_agent   as _ctx_get_current_agent,
)
from modules.turns_list import delete_turns_list

# Use a reentrant lock so set_current_agent_tuple can call itself safely.
_current_agent_lock = threading.RLock()
_current_agent: Optional[Tuple[str, str, str]] = None    # (role, id, repo)
_agent_stack: List[Tuple[str, str, str]] = []            # LIFO stack of (role, id, repo)

def _cache_init_current_agent():
    """
    On import: load persisted pointer and seed our stack.
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
    """
    ctx = _ctx_get_current_agent()
    if ctx and any(ctx):
        return ctx
    return _current_agent

def set_current_agent_tuple(
    agent_role: Optional[str],
    agent_id:   Optional[str],
    repo_url:   Optional[str]
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

        if agent_role and agent_id and repo_url:
            _agent_stack.append((agent_role, agent_id, repo_url))
            db_save_current_agent_pointer(agent_role, agent_id, repo_url)
            _current_agent = (agent_role, agent_id, repo_url)
        else:
            # clearing
            db_delete_current_agent_pointer()
            _agent_stack.clear()
            _current_agent = None

def seed_root_agent(repo_url: str) -> str:
    """
    Ensure a 'root' agent exists (role="root", id="001"), make it current,
    and push it onto the stack.
    """
    for row in db_list_running_agents(repo_url):
        if row["agent_role"] == "root":
            rid = row["agent_id"]
            set_current_agent_tuple("root", rid, repo_url)
            return rid

    new_row = db_add_running_agent("root", repo_url)
    rid = new_row["agent_id"]
    set_current_agent_tuple("root", rid, repo_url)
    return rid

def list_running_agents(repo_url: Optional[str] = None) -> List[dict]:
    """
    List all agents for a repo; default to current's repo if None.
    """
    if repo_url is None:
        tup = get_current_agent_tuple()
        if not tup:
            return []
        _, _, repo_url = tup

    return db_list_running_agents(repo_url)

def get_current_running_agent(repo_url: Optional[str] = None) -> dict:
    """
    Return the dict for the current agent, or {} if none.
    """
    if repo_url is None:
        tup = get_current_agent_tuple()
        if not tup:
            return {}
        _, _, repo_url = tup

    ca = get_current_agent_tuple()
    if not ca or ca[2] != repo_url:
        return {}

    for a in db_list_running_agents(repo_url):
        if a["agent_role"] == ca[0] and a["agent_id"] == ca[1]:
            return a
    return {}

def set_current_agent(agent_role: str, agent_id: str, repo_url: str) -> dict:
    """
    Public API: pick an existing agent as current.
    """
    agents = db_list_running_agents(repo_url)
    if not any(a["agent_role"] == agent_role and a["agent_id"] == agent_id for a in agents):
        raise RuntimeError(f"Agent {agent_role}:{agent_id} not found in repo '{repo_url}'")
    set_current_agent_tuple(agent_role, agent_id, repo_url)
    return {"message": f"Current agent set to {agent_role}:{agent_id} in repo '{repo_url}'"}

def add_running_agent(agent_role: str, repo_url: str) -> dict:
    """
    Public API: add a new agent. If this is the very first non-root
    agent in a brand-new repo, seed the root first.
    """
    existing = db_list_running_agents(repo_url)
    if not existing and agent_role != "root":
        seed_root_agent(repo_url)

    return db_add_running_agent(agent_role, repo_url)

def remove_running_agent(agent_role: str, agent_id: str, repo_url: str) -> dict:
    """
    Public API:
      0) Forbid removing the special root:001
      1) Forbid removing any agent that’s currently on the call-stack.
      2) Delete from DB and purge turns.
      3) (Should never fire now) If it was the current/top, pop the stack and restore.
    """
    # 0) cannot delete root:001
    if agent_role == "root" and agent_id == "001":
        raise RuntimeError("Cannot remove the root agent")

    target = (agent_role, agent_id, repo_url)

    # 1) forbid removal of any agent on the call-stack
    with _current_agent_lock:
        if target in _agent_stack:
            raise RuntimeError("Cannot remove agent still in call-stack")

    # 2) delete and purge
    count = db_remove_running_agent(agent_role, agent_id, repo_url)
    delete_turns_list(agent_role, agent_id, repo_url)

    # 3) (In normal operation this will never fire, since we already blocked
    #    removal of any agent on the stack.  We leave it here for safety.)
    with _current_agent_lock:
        if _agent_stack and _agent_stack[-1] == target:
            _agent_stack.pop()
            if _agent_stack:
                set_current_agent_tuple(*_agent_stack[-1])
            else:
                # empty → fall back to root
                seed_root_agent(repo_url)

    if count == 0:
        raise RuntimeError(f"No such running agent {agent_role}:{agent_id} in repo '{repo_url}'")

    return {"message": f"Removed running agent {agent_role}:{agent_id} from repo '{repo_url}'"}

def get_agent_stack() -> List[Dict[str, str]]:
    """
    Return a snapshot of the current agent call-stack
    (from bottom to top) as a list of dicts with keys:
    agent_role, agent_id, repo_url.
    """
    with _current_agent_lock:
        return [
            {"agent_role": role, "agent_id": aid, "repo_url": repo}
            for role, aid, repo in _agent_stack
        ]
