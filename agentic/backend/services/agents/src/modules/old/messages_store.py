# modules/messages_store.py

import sqlite3
import json
from typing import List, Dict, Any

from shared.config import config
from shared.logger import logger

DB_PATH = config["MESSAGES_DB_FILE"]

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    with conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_role TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            meta TEXT NOT NULL
        );
        """)
    conn.close()
    logger.info(f"messages_store_sqlite: Initialized DB at {DB_PATH}")

def insert_message(agent_role: str, agent_id: str, message: Dict[str, Any]):
    conn = get_conn()
    with conn:
        conn.execute("""
            INSERT INTO messages
                (agent_role, agent_id, message_id, role, content, meta)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(agent_role),
            str(agent_id),
            int(message["message_id"]),
            str(message["role"]),
            str(message.get("content", "")),
            json.dumps(message.get("meta", {})),
        ))
    conn.close()
    logger.info(
        f"messages_store_sqlite: Inserted message_id={message.get('message_id')} for {agent_role}/{agent_id}"
    )

def insert_messages_batch(agent_role: str, agent_id: str, messages: List[Dict[str, Any]]):
    conn = get_conn()
    with conn:
        conn.executemany("""
            INSERT INTO messages
                (agent_role, agent_id, message_id, role, content, meta)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (
                str(agent_role),
                str(agent_id),
                int(m.get("message_id", 0)),
                str(m.get("role", "")),
                str(m.get("content", "")),
                json.dumps(m.get("meta", {})),
            ) for m in messages
        ])
    conn.close()
    logger.info(
        f"messages_store_sqlite: Inserted batch of {len(messages)} messages for {agent_role}/{agent_id}"
    )

def fetch_messages(agent_role: str, agent_id: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM messages WHERE agent_role=? AND agent_id=?
        ORDER BY message_id ASC
    """, (str(agent_role), str(agent_id)))
    rows = cur.fetchall()
    conn.close()
    msgs = []
    for row in rows:
        meta = row["meta"]
        meta = json.loads(meta) if meta else {}
        msgs.append(dict(
            message_id=row["message_id"],
            role=row["role"],
            content=row["content"],
            meta=meta,
        ))
    return msgs

if __name__ == "__main__":
    init_db()
