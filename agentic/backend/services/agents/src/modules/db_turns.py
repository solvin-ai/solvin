# modules/db_turns.py

from datetime import datetime
from typing import List, Optional

from modules.db import get_db
from modules.db_tool_meta import save_tool_meta, load_tool_meta
from modules.db_messages import save_messages, load_messages
from modules.unified_turn import UnifiedTurn

def save_turns(repo_url: str, agent_role: str, agent_id: str, turns: List[UnifiedTurn]):
    """
    Overwrite all finalized turns for (repo,role,id).
    Each write uses an independent DB connection to avoid lock contention.
    """
    # 1) Wipe existing turns
    with get_db() as db:
        db.execute(
            "DELETE FROM turns WHERE repo_url=? AND agent_role=? AND agent_id=?",
            (repo_url, agent_role, agent_id)
        )
    # 2) Insert/update each turn, its tool_meta, and its messages
    for turn in turns:
        td    = turn.turn_meta
        idx   = td["turn"]
        total = td.get("total_char_count", 0)

        # a) Upsert the turn row
        with get_db() as db:
            db.execute(
                """
                INSERT INTO turns
                  (repo_url, agent_role, agent_id, turn_idx, total_char_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(repo_url, agent_role, agent_id, turn_idx)
                DO UPDATE SET total_char_count = excluded.total_char_count
                """,
                (repo_url, agent_role, agent_id, idx, total),
            )
        # b) Persist tool_meta
        save_tool_meta(repo_url, agent_role, agent_id, idx, turn.tool_meta)
        # c) Persist messages
        save_messages(repo_url, agent_role, agent_id, idx, turn.messages)


def load_turns(repo_url: str, agent_role: str, agent_id: str) -> List[UnifiedTurn]:
    """
    Load all turns (as UnifiedTurn) for (repo,role,id), in turn_idx order.
    """
    with get_db() as db:
        rows = db.execute(
            """
            SELECT turn_idx, total_char_count
              FROM turns
             WHERE repo_url=? AND agent_role=? AND agent_id=?
             ORDER BY turn_idx
            """,
            (repo_url, agent_role, agent_id),
        ).fetchall()

    result: List[UnifiedTurn] = []
    for r in rows:
        idx = r["turn_idx"]
        turn_meta = {
            "turn": idx,
            "finalized": True,
            "total_char_count": r["total_char_count"],
        }
        tm   = load_tool_meta(repo_url, agent_role, agent_id, idx)
        msgs = load_messages(repo_url, agent_role, agent_id, idx)
        result.append(UnifiedTurn(turn_meta, tm, msgs))

    return result


def query_turns(
    repo_url:  str,
    agent_role: str,
    agent_id:   str,
    limit:      int                    = 50,
    offset:     int                    = 0,
    status:     Optional[str]          = None,
    tool_name:  Optional[str]          = None,
    deleted:    Optional[bool]         = None,
    sort:       Optional[List[str]]    = None,
) -> List[UnifiedTurn]:
    """
    Load a page of turns with optional filters and sort.
    Joins turns → tool_meta, applies WHERE clauses, ORDER BY, LIMIT/OFFSET.
    """
    clauses = ["t.repo_url = ?", "t.agent_role = ?", "t.agent_id = ?"]
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
            # choose table alias
            if name in ("turn_idx", "total_char_count"):
                col = f"t.{name}"
            else:
                col = f"tm.{name}"
            direction = "DESC" if desc else "ASC"
            parts.append(f"{col} {direction}")
        if parts:
            order_sql = ", ".join(parts)

    sql = f"""
      SELECT t.turn_idx, t.total_char_count
        FROM turns t
        JOIN tool_meta tm
          ON tm.repo_url = t.repo_url
         AND tm.agent_role = t.agent_role
         AND tm.agent_id   = t.agent_id
         AND tm.turn_idx   = t.turn_idx
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
        idx = r["turn_idx"]
        turn_meta = {
            "turn": idx,
            "finalized": True,
            "total_char_count": r["total_char_count"],
        }
        tm   = load_tool_meta(repo_url, agent_role, agent_id, idx)
        msgs = load_messages(repo_url, agent_role, agent_id, idx)
        result.append(UnifiedTurn(turn_meta, tm, msgs))

    return result


def delete_turns(repo_url: str, agent_role: str, agent_id: str):
    """
    Wipe all turns for (repo,role,id).  Cascades into tool_meta & messages.
    """
    with get_db() as db:
        db.execute(
            "DELETE FROM turns WHERE repo_url=? AND agent_role=? AND agent_id=?",
            (repo_url, agent_role, agent_id)
        )
