# modules/db_tool_meta.py

import json
from contextlib import closing
from modules.db import get_db

def save_tool_meta(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    turn_idx: int,
    tm: dict
):
    """
    Upsert one row into tool_meta for the given turn and task.
    Serializes structured fields (args, rejection, filenames) to JSON so they
    can be safely bound into SQLite.

    Scoped by (repo_url, agent_role, agent_id).
    """
    normalized_args_json     = json.dumps(tm.get("normalized_args", {}))
    input_args_json          = json.dumps(tm.get("input_args", {}))
    rejection_json           = json.dumps(tm.get("rejection", None))
    normalized_filename_json = json.dumps(tm.get("normalized_filename", []))

    with get_db() as db:
        db.execute("""
          INSERT INTO tool_meta (
            repo_url,
            agent_role,
            agent_id,
            turn_idx,
            tool_name,
            execution_time,
            pending_deletion,
            deleted,
            rejection,
            status,
            args_hash,
            preservation_policy,
            normalized_args_json,
            normalized_filename,
            input_args_json
          ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
          )
          ON CONFLICT(repo_url,agent_role,agent_id,turn_idx) DO UPDATE SET
            tool_name            = excluded.tool_name,
            execution_time       = excluded.execution_time,
            pending_deletion     = excluded.pending_deletion,
            deleted              = excluded.deleted,
            rejection            = excluded.rejection,
            status               = excluded.status,
            args_hash            = excluded.args_hash,
            preservation_policy  = excluded.preservation_policy,
            normalized_args_json = excluded.normalized_args_json,
            normalized_filename  = excluded.normalized_filename,
            input_args_json      = excluded.input_args_json
        """, (
            repo_url,
            agent_role,
            agent_id,
            turn_idx,
            tm.get("tool_name"),
            tm.get("execution_time", 0.0),
            int(bool(tm.get("pending_deletion"))),
            int(bool(tm.get("deleted"))),
            rejection_json,
            tm.get("status"),
            tm.get("args_hash"),
            tm.get("preservation_policy"),
            normalized_args_json,
            normalized_filename_json,
            input_args_json,
        ))
        db.commit()

def load_tool_meta(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    turn_idx: int
) -> dict:
    """
    Returns a dict suitable for UnifiedTurn.tool_meta.
    Parses JSON back into Python objects for the JSON columns.

    Scoped by (repo_url, agent_role, agent_id).
    """
    with get_db() as db:
        row = db.execute("""
          SELECT *
            FROM tool_meta
           WHERE repo_url=? AND agent_role=? AND agent_id=? AND turn_idx=?
        """, (repo_url, agent_role, agent_id, turn_idx)).fetchone()

        if not row:
            return {}

        return {
            "tool_name":           row["tool_name"],
            "execution_time":      row["execution_time"],
            "pending_deletion":    bool(row["pending_deletion"]),
            "deleted":             bool(row["deleted"]),
            "rejection":           json.loads(row["rejection"]),
            "status":              row["status"],
            "args_hash":           row["args_hash"],
            "preservation_policy": row["preservation_policy"],
            "normalized_args":     json.loads(row["normalized_args_json"] or "{}"),
            "normalized_filename": json.loads(row["normalized_filename"] or "[]"),
            "input_args":          json.loads(row["input_args_json"] or "{}"),
        }

def delete_tool_meta(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    turn_idx: int
):
    """
    Deletes a tool_meta row for the given turn and task.

    Scoped by (repo_url, agent_role, agent_id).
    """
    with get_db() as db:
        db.execute("""
          DELETE
            FROM tool_meta
           WHERE repo_url=? AND agent_role=? AND agent_id=? AND turn_idx=?
        """, (repo_url, agent_role, agent_id, turn_idx))
        db.commit()
