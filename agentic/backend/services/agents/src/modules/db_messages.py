# modules/db_messages.py

import json
from modules.db import get_db
from modules.db_state import allocate_next_message_id

def save_messages(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    turn_idx: int,
    messages: dict   # role → { raw:…, meta:… }
):
    """
    Overwrite all messages for this turn.

    Pre-allocates any missing original_message_id values before
    opening the main DB connection to avoid nested writer locks.
    """
    # 1) Pre-allocate any missing original_message_id
    for mdata in messages.values():
        meta = mdata["meta"]
        if meta.get("original_message_id") is None:
            meta["original_message_id"] = allocate_next_message_id(
                repo_url, agent_role, agent_id
            )

    # 2) Delete existing messages and re-insert all messages in one transaction
    with get_db() as db:
        db.execute("""
          DELETE FROM messages
          WHERE repo_url=? AND agent_role=? AND agent_id=? AND turn_idx=?
        """, (repo_url, agent_role, agent_id, turn_idx))

        for msg_idx, (role, mdata) in enumerate(messages.items()):
            raw     = mdata["raw"].copy()
            content = raw.pop("content", "") or ""
            meta    = mdata["meta"]

            db.execute("""
              INSERT INTO messages (
                repo_url,agent_role,agent_id,turn_idx,message_idx,
                role,content,timestamp,original_message_id,char_count,raw_json
              ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
              repo_url,
              agent_role,
              agent_id,
              turn_idx,
              msg_idx,
              role,
              content,
              meta["timestamp"],
              meta["original_message_id"],
              meta["char_count"],
              json.dumps(raw) if raw else None
            ))
        db.commit()

def load_messages(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    turn_idx: int
) -> dict:
    """
    Returns messages mapping role→{ raw:…, meta:… }
    """
    with get_db() as db:
        rows = db.execute("""
          SELECT * FROM messages
          WHERE repo_url=? AND agent_role=? AND agent_id=? AND turn_idx=?
          ORDER BY message_idx
        """, (repo_url, agent_role, agent_id, turn_idx)).fetchall()

    out = {}
    for r in rows:
        raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        raw["role"]    = r["role"]
        raw["content"] = r["content"]
        meta = {
          "timestamp":           r["timestamp"],
          "original_message_id": r["original_message_id"],
          "char_count":          r["char_count"]
        }
        out[r["role"]] = {"raw": raw, "meta": meta}
    return out

def delete_messages(
    repo_url: str,
    agent_role: str,
    agent_id: str,
    turn_idx: int
):
    with get_db() as db:
        db.execute("""
          DELETE FROM messages
          WHERE repo_url=? AND agent_role=? AND agent_id=? AND turn_idx=?
        """, (repo_url, agent_role, agent_id, turn_idx))
        db.commit()