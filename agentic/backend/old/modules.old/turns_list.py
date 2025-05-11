# modules/turns_list.py

from typing import Optional
import time
from modules.state_manager import load_turns_list, save_turns_list, delete_turns_list as _state_delete_turns_list
from modules.agent_manager import list_live_agents, get_running_agent

# Configuration: maximum number of turns lists to keep in memory.
MAX_TURNS_LISTS_IN_MEMORY = 10

_turns_lists = {}     # Keys: (agent_role, agent_id)
_lru_tracker = {}     # For LRU tracking

def get_turns_list(agent_role: Optional[str] = None, agent_id: Optional[str] = None) -> list:
    """
    Retrieves the conversation history for the given agent.
    If agent_role or agent_id aren't provided, use the currently running agent,
    as determined by modules.agent_manager.get_running_agent().
    """
    if agent_role is None or agent_id is None:
        agent_role, agent_id = get_running_agent()
    key = (agent_role, agent_id)
    if key not in _turns_lists:
        if any(agent for agent in list_live_agents() if agent.get('agent_role') == agent_role and agent.get('agent_id') == agent_id):
            loaded = load_turns_list(agent_role, agent_id)
            _turns_lists[key] = loaded if loaded is not None else []
        else:
            _turns_lists[key] = []
    _lru_tracker[key] = time.time()
    return _turns_lists[key]

def append_turn(agent_role: str, agent_id: str, turn) -> None:
    turns = get_turns_list(agent_role, agent_id)
    turns.append(turn)
    _lru_tracker[(agent_role, agent_id)] = time.time()

def save_and_purge_turns_list(agent_role: str, agent_id: str) -> None:
    key = (agent_role, agent_id)
    if key in _turns_lists:
        save_turns_list(_turns_lists[key], agent_role, agent_id)
    _purge_old_turns_lists()

def _purge_old_turns_lists() -> None:
    while len(_turns_lists) > MAX_TURNS_LISTS_IN_MEMORY:
        lru_key = min(_lru_tracker, key=lambda k: _lru_tracker[k])
        _turns_lists.pop(lru_key, None)
        _lru_tracker.pop(lru_key, None)

def delete_turns_list(agent_role: str, agent_id: str) -> None:
    key = (agent_role, agent_id)
    if key in _turns_lists:
        del _turns_lists[key]
    if key in _lru_tracker:
        del _lru_tracker[key]
    _state_delete_turns_list(agent_role, agent_id)
