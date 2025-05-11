# modules/agents_registry.py

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import os
import json

router = APIRouter()

BASE_DIR = os.getcwd()
DB_FILE = os.path.join(BASE_DIR, "agents_registry.sqlite")

def get_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db

def initialize_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS agents_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_role TEXT UNIQUE NOT NULL,
            agent_description TEXT DEFAULT '',
            allowed_tools TEXT,
            default_developer_prompt TEXT DEFAULT ''
        );
    """)
    db.commit()
    db.close()

initialize_db()

class AgentRegistryItem(BaseModel):
    id: Optional[int] = None
    agent_role: str
    agent_description: str = ""
    allowed_tools: List[str] = []
    default_developer_prompt: str = ""

@router.get("/agents/registry/list", response_model=List[AgentRegistryItem])
def list_registry():
    db = get_db()
    rows = db.execute("SELECT * FROM agents_registry ORDER BY id").fetchall()
    db.close()
    return [
        AgentRegistryItem(
            id=row["id"],
            agent_role=row["agent_role"],
            agent_description=row["agent_description"],
            allowed_tools=json.loads(row["allowed_tools"] or "[]"),
            default_developer_prompt=row["default_developer_prompt"] or "",
        )
        for row in rows
    ]

@router.post("/agents/registry/upsert", response_model=AgentRegistryItem)
def upsert_agent_role(item: AgentRegistryItem):
    db = get_db()
    if item.id:
        row = db.execute("SELECT id FROM agents_registry WHERE id = ?", (item.id,)).fetchone()
    else:
        row = db.execute("SELECT id FROM agents_registry WHERE agent_role = ?", (item.agent_role,)).fetchone()
    allowed_tools_json = json.dumps(item.allowed_tools or [])
    if row:
        db.execute(
            """
            UPDATE agents_registry
            SET agent_role = ?, agent_description = ?, allowed_tools = ?, default_developer_prompt = ?
            WHERE id = ?
            """,
            (
                item.agent_role,
                item.agent_description,
                allowed_tools_json,
                item.default_developer_prompt,
                row["id"]
            ),
        )
        item.id = row["id"]
    else:
        cur = db.execute(
            """
            INSERT INTO agents_registry (agent_role, agent_description, allowed_tools, default_developer_prompt)
            VALUES (?, ?, ?, ?)
            """,
            (
                item.agent_role,
                item.agent_description,
                allowed_tools_json,
                item.default_developer_prompt,
            ),
        )
        item.id = cur.lastrowid
    db.commit()
    db.close()
    return item

@router.delete("/agents/registry/delete")
def delete_agent_role(id: int = Query(...)):
    db = get_db()
    cur = db.execute("DELETE FROM agents_registry WHERE id = ?", (id,))
    db.commit()
    db.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Agent registry entry not found")
    return {"message": "Agent registry entry deleted successfully."}
