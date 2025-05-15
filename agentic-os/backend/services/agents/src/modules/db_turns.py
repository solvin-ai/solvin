# modules/db_turns.py

"""
Persist and load UnifiedTurn histories, now scoped by (repo_url, agent_role, agent_id),
plus conversation‐level metadata.  We’ve added two new per‐turn fields:
  • invocation_reason   TEXT
  • turns_to_purge      TEXT  -- JSON‐encoded list of ints
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from modules.db import get_db
from modules.db_tool_meta import save_tool_meta, load_tool_meta
from modules.db_messages import save_messages, load_messages
from modules.unified_turn import UnifiedTurn


def save_turns(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    turns: List[UnifiedTurn]
):
    """
    Overwrite all finalized turns for (repo_url,agent_role,agent_id).
    Each write uses an independent DB connection to avoid lock contention.
    """
    # 1) wipe existing turns
    with get_db() as db:
        db.execute(
            "DELETE FROM turns WHERE repo_url=? AND agent_role=? AND agent_id=?",
            (repo_url, agent_role, agent_id)
        )

    # 2) insert/update each turn, its tool_meta, and its messages
    for turn in turns:
        td    = turn.turn_meta
        idx   = td["turn"]
        total = td.get("total_char_count", 0)

        # new fields
        invocation_reason = td.get("invocation_reason")
        turns_to_purge    = td.get("turns_to_purge", [])
        # JSON-encode the list (safe if it’s already a list of ints)
        ttp_blob = json.dumps(turns_to_purge)

        # a) upsert the turn row, now including our two new columns
        with get_db() as db:
            db.execute(
                """
                INSERT INTO turns
                  (repo_url, agent_role, agent_id,
                   turn_idx, total_char_count,
                   invocation_reason, turns_to_purge)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_url, agent_role, agent_id, turn_idx)
                DO UPDATE SET
                  total_char_count   = excluded.total_char_count,
                  invocation_reason  = excluded.invocation_reason,
                  turns_to_purge     = excluded.turns_to_purge
                """,
                (
                  repo_url,
                  agent_role,
                  agent_id,
                  idx,
                  total,
                  invocation_reason,
                  ttp_blob
                ),
            )

        # b) persist tool_meta
        save_tool_meta(repo_url, agent_role, agent_id, idx, turn.tool_meta)
        # c) persist messages
        save_messages(repo_url, agent_role, agent_id, idx, turn.messages)


def load_turns(
    repo_url: str,
    agent_role: str,
    agent_id: str
) -> List[UnifiedTurn]:
    """
    Load all turns (as UnifiedTurn) for (repo_url,agent_role,agent_id),
    in turn_idx order.
    """
    with get_db() as db:
        rows = db.execute(
            """
            SELECT turn_idx,
                   total_char_count,
                   invocation_reason,
                   turns_to_purge
              FROM turns
             WHERE repo_url=? AND agent_role=? AND agent_id=?
             ORDER BY turn_idx
            """,
            (repo_url, agent_role, agent_id),
        ).fetchall()

    result: List[UnifiedTurn] = []
    for r in rows:
        idx                = r["turn_idx"]
        total              = r["total_char_count"]
        invocation_reason  = r["invocation_reason"]
        # parse the JSON-blob back into a list of ints
        ttp_list = []
        if r["turns_to_purge"]:
            try:
                ttp_list = json.loads(r["turns_to_purge"])
            except json.JSONDecodeError:
                ttp_list = []

        turn_meta = {
            "turn":              idx,
            "finalized":         True,
            "total_char_count":  total,
            "invocation_reason": invocation_reason,
            "turns_to_purge":    ttp_list,
        }
        tm   = load_tool_meta(repo_url, agent_role, agent_id, idx)
        msgs = load_messages(repo_url, agent_role, agent_id, idx)
        result.append(UnifiedTurn(turn_meta, tm, msgs))

    return result


def query_turns(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    tool_name: Optional[str] = None,
    deleted: Optional[bool] = None,
    sort: Optional[List[str]] = None,
) -> List[UnifiedTurn]:
    """
    Load a page of turns with optional filters and sort.
    Joins turns → tool_meta, applies WHERE clauses, ORDER BY, LIMIT/OFFSET.
    Scoped by (repo_url,agent_role,agent_id).
    """
    clauses = [
        "t.repo_url = ?",
        "t.agent_role = ?",
        "t.agent_id = ?",
    ]
    params = [repo_url, agent_role, agent_id]

    if status is not None:
        clauses.append("tm.status = ?")
        params.append(status)
    if tool_name is not None:
        clauses.append("tm.tool_name = ?")
        params.append(tool_name)
    if deleted is not None:
        clauses.append("tm.deleted = ?")
        params.append(int(deleted))

    where_sql = " AND ".join(clauses)

    # Build ORDER BY
    order_sql = "t.turn_idx ASC"
    if sort:
        parts = []
        for field in sort:
            desc = field.startswith("-")
            name = field[1:] if desc else field
            if name in ("turn_idx", "total_char_count"):
                col = f"t.{name}"
            else:
                col = f"tm.{name}"
            direction = "DESC" if desc else "ASC"
            parts.append(f"{col} {direction}")
        if parts:
            order_sql = ", ".join(parts)

    sql = f"""
      SELECT t.turn_idx,
             t.total_char_count,
             t.invocation_reason,
             t.turns_to_purge
        FROM turns t
        JOIN tool_meta tm
          ON tm.repo_url    = t.repo_url
         AND tm.agent_role  = t.agent_role
         AND tm.agent_id    = t.agent_id
         AND tm.turn_idx    = t.turn_idx
       WHERE {where_sql}
    ORDER BY {order_sql}
       LIMIT ?
      OFFSET ?
    """
    params.extend([limit, offset])

    with get_db() as db:
        rows = db.execute(sql, params).fetchall()

    result: List[UnifiedTurn] = []
    for r in rows:
        idx               = r["turn_idx"]
        total             = r["total_char_count"]
        invocation_reason = r["invocation_reason"]
        # decode JSON
        ttp_list = []
        if r["turns_to_purge"]:
            try:
                ttp_list = json.loads(r["turns_to_purge"])
            except json.JSONDecodeError:
                ttp_list = []

        turn_meta = {
            "turn":              idx,
            "finalized":         True,
            "total_char_count":  total,
            "invocation_reason": invocation_reason,
            "turns_to_purge":    ttp_list,
        }
        tm   = load_tool_meta(repo_url, agent_role, agent_id, idx)
        msgs = load_messages(repo_url, agent_role, agent_id, idx)
        result.append(UnifiedTurn(turn_meta, tm, msgs))

    return result


def delete_turns(
    repo_url: str,
    agent_role: str,
    agent_id: str
):
    """
    Wipe all turns for (repo_url,agent_role,agent_id).
    Cascades into tool_meta & messages.
    """
    with get_db() as db:
        db.execute(
            "DELETE FROM turns WHERE repo_url=? AND agent_role=? AND agent_id=?",
            (repo_url, agent_role, agent_id)
        )


# ------------------------------------------------------------------------
# Conversation‐level metadata persistence
# ------------------------------------------------------------------------

def save_conversation_metadata(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    metadata: Dict[str, Any]
) -> None:
    """
    Upsert the entire conversation‐level metadata dict as JSON.
    """
    blob = json.dumps(metadata)
    with get_db() as db:
        db.execute(
            """
            INSERT INTO conversation_metadata
              (repo_url, agent_role, agent_id, metadata)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(repo_url, agent_role, agent_id)
            DO UPDATE SET metadata = excluded.metadata
            """,
            (repo_url, agent_role, agent_id, blob),
        )


def load_conversation_metadata(
    repo_url: str,
    agent_role: str,
    agent_id: str
) -> Dict[str, Any]:
    """
    Load the conversation metadata JSON (or return {} if not present or invalid).
    """
    with get_db() as db:
        row = db.execute(
            """
            SELECT metadata
              FROM conversation_metadata
             WHERE repo_url=? AND agent_role=? AND agent_id=?
            """,
            (repo_url, agent_role, agent_id),
        ).fetchone()

    if not row or not row["metadata"]:
        return {}
    try:
        return json.loads(row["metadata"])
    except json.JSONDecodeError:
        return {}
