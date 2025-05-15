# modules/db_state.py

"""
Agent‐state table helpers: monotonic counters for turn_idx & message_id,
and resetting state when a conversation is cleared.

State is scoped to (repo_url, agent_role, agent_id).
"""

from typing import Tuple, Optional
from modules.db import get_db


def allocate_next_turn_idx(
    repo_url: str,
    agent_role: str,
    agent_id: str
) -> int:
    """
    Atomically read & bump last_turn_idx in agent_state.
    Returns the newly allocated turn_idx (starting at 0).
    Scoped by (repo_url, agent_role, agent_id).
    """
    with get_db() as db:
        # fetch existing state (if any)
        row = db.execute(
            "SELECT last_turn_idx FROM agent_state "
            "WHERE repo_url=? AND agent_role=? AND agent_id=?",
            (repo_url, agent_role, agent_id)
        ).fetchone()
        last = row["last_turn_idx"] if row else -1

        new_turn_idx = last + 1

        # upsert the new turn_idx, preserving last_message_id
        db.execute(
            """
            INSERT INTO agent_state
              (repo_url, agent_role, agent_id, last_turn_idx, last_message_id)
            VALUES (
              ?, ?, ?, ?,
              COALESCE((
                SELECT last_message_id FROM agent_state
                 WHERE repo_url=? AND agent_role=? AND agent_id=?
              ), -1)
            )
            ON CONFLICT(repo_url, agent_role, agent_id) DO UPDATE
              SET last_turn_idx = excluded.last_turn_idx
            """,
            (
                repo_url,
                agent_role,
                agent_id,
                new_turn_idx,
                # these three feed the SELECT inside COALESCE
                repo_url,
                agent_role,
                agent_id,
            )
        )
        return new_turn_idx


def allocate_next_message_id(
    repo_url: str,
    agent_role: str,
    agent_id: str
) -> int:
    """
    Atomically read & bump last_message_id in agent_state.
    Returns the newly allocated original_message_id (starting at 0).
    Scoped by (repo_url, agent_role, agent_id).
    """
    with get_db() as db:
        # fetch existing state (if any)
        row = db.execute(
            "SELECT last_message_id, last_turn_idx FROM agent_state "
            "WHERE repo_url=? AND agent_role=? AND agent_id=?",
            (repo_url, agent_role, agent_id)
        ).fetchone()
        last_msg   = row["last_message_id"] if row else -1
        carry_turn = row["last_turn_idx"]    if row else -1

        new_msg_id = last_msg + 1

        # upsert the new message_id, preserving last_turn_idx
        db.execute(
            """
            INSERT INTO agent_state
              (repo_url, agent_role, agent_id, last_turn_idx, last_message_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(repo_url, agent_role, agent_id) DO UPDATE
              SET last_message_id = excluded.last_message_id
            """,
            (repo_url, agent_role, agent_id, carry_turn, new_msg_id)
        )
        return new_msg_id


def load_state(
    repo_url: str,
    agent_role: str,
    agent_id: str
) -> Tuple[int, int]:
    """
    Return (last_turn_idx, last_message_id) for this conversation,
    or (-1, -1) if no state row exists yet.
    Scoped by (repo_url, agent_role, agent_id).
    """
    with get_db() as db:
        row = db.execute(
            "SELECT last_turn_idx, last_message_id FROM agent_state "
            "WHERE repo_url=? AND agent_role=? AND agent_id=?",
            (repo_url, agent_role, agent_id)
        ).fetchone()
    if not row:
        return -1, -1
    return row["last_turn_idx"], row["last_message_id"]


def save_state(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    last_turn_idx: Optional[int]   = None,
    last_message_id: Optional[int] = None
) -> None:
    """
    Upsert the given fields into agent_state.
    If you pass None for one of the counters it will preserve the existing
    value for that column.
    Scoped by (repo_url, agent_role, agent_id).
    """
    # first read the existing
    cur_turn, cur_msg = load_state(repo_url, agent_role, agent_id)
    nt = last_turn_idx    if last_turn_idx    is not None else cur_turn
    nm = last_message_id  if last_message_id  is not None else cur_msg

    with get_db() as db:
        db.execute(
            """
            INSERT INTO agent_state
              (repo_url, agent_role, agent_id, last_turn_idx, last_message_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(repo_url, agent_role, agent_id)
            DO UPDATE SET
              last_turn_idx    = excluded.last_turn_idx,
              last_message_id  = excluded.last_message_id
            """,
            (repo_url, agent_role, agent_id, nt, nm)
        )


def delete_state(
    repo_url: str,
    agent_role: str,
    agent_id: str
) -> None:
    """
    Reset the agent_state for this conversation so that
    next allocations start again at 0.
    Scoped by (repo_url, agent_role, agent_id).
    """
    with get_db() as db:
        db.execute(
            "DELETE FROM agent_state "
            "WHERE repo_url=? AND agent_role=? AND agent_id=?",
            (repo_url, agent_role, agent_id)
        )
