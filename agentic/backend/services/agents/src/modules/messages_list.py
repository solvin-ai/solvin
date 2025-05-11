# modules/messages_list.py

"""
A read‐only view of your existing turns/messages tables,
plus a helper to append one turn containing multiple messages.

append_messages() does NOT invoke any LLM or tool execution—it only persists
a new turn with one or more messages into your history.
"""

from typing import List, Dict, Any, Optional, Union

from modules.turns_list import get_turns_list, add_turn_to_list, save_turns_list
from modules.unified_turn import UnifiedTurn
from modules.db_state import allocate_next_message_id


def get_messages_list(
    agent_role: str,
    agent_id:   str,
    repo_url:  str,
    role:       Optional[str] = None,
    turn_id:    Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Read‐only: return every message (across all turns) for this agent,
    optionally filtered by role or by a single turn_id.
    """
    turns: List[UnifiedTurn] = get_turns_list(agent_role, agent_id, repo_url)
    out: List[Dict[str, Any]] = []
    for turn in turns:
        t_idx = turn.turn_meta["turn"]
        if turn_id is not None and t_idx != turn_id:
            continue

        for _key, msg in turn.messages.items():
            # Pull the true role out of the raw record, not the dict key
            raw = msg["raw"].copy()
            content = raw.pop("content", "")
            msg_role = raw.get("role")

            if role is not None and role != msg_role:
                continue

            out.append({
                "turn":       t_idx,
                "message_id": msg["meta"]["original_message_id"],
                "role":       msg_role,
                "content":    content,
                "meta":       msg["meta"].copy(),
                "raw":        raw
            })

    return out


def get_message_by_id(
    agent_role: str,
    agent_id:   str,
    repo_url:  str,
    message_id: int
) -> Optional[Dict[str, Any]]:
    """
    Lookup a single message by its original_message_id.
    """
    for m in get_messages_list(agent_role, agent_id, repo_url):
        if m["message_id"] == message_id:
            return m
    return None


def append_messages(
    agent_role: str,
    agent_id:   str,
    role:       str,
    messages:   Union[str, List[str]],
    repo_url:  str,
    **extra_fields: Any
) -> Dict[str, Any]:
    """
    Append a single new turn containing one or more messages under `role`.
    If `messages` is a list, each string becomes its own message in the same turn.

    Returns:
        dict: {
          "turn_id": int,
          "message_ids": List[int]
        }
    """

    # 1) normalize to a Python list
    if isinstance(messages, str):
        msgs = [messages]
    else:
        msgs = messages

    # 2) allocate one message_id per entry, persisted in agent_state
    msg_ids = [
        allocate_next_message_id(repo_url, agent_role, agent_id)
        for _ in msgs
    ]

    # 3) build the new turn (no messages yet)
    history  = get_turns_list(agent_role, agent_id, repo_url)
    next_idx = len(history)
    ut = UnifiedTurn.create_turn(
        {"turn": next_idx, "finalized": True},
        {}   # we'll inject messages below
    )

    # 4) inject each message into the same turn
    for content, mid in zip(msgs, msg_ids):
        ut.add_message(
            role=role,
            content=content,
            original_message_id=mid
        )

    # 5) persist the new turn
    add_turn_to_list(agent_role, agent_id, repo_url, ut)
    save_turns_list(agent_role, agent_id, repo_url)

    # 6) return the new turn index and message ids
    return {
        "turn_id":      ut.turn_meta["turn"],
        "message_ids":  msg_ids
    }