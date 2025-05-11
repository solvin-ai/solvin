# modules/db_agents.py

from typing import List, Optional, Tuple
from contextlib import closing

from modules.db import get_db


def initialize_agents_db():
    """
    Create or migrate the agents_running and agents_current tables in the shared SQLite file.
    """
    with get_db() as db:
        # ----- agents_running -----
        cols = db.execute("PRAGMA table_info(agents_running)").fetchall()
        if not cols:
            db.execute("""
              CREATE TABLE agents_running (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_role   TEXT    NOT NULL,
                agent_id     TEXT    NOT NULL,
                repo_url     TEXT    NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
              );
            """)
        else:
            names = [c["name"] for c in cols]
            if "repo_url" not in names:
                db.execute(
                  "ALTER TABLE agents_running ADD COLUMN repo_url TEXT NOT NULL DEFAULT '';"
                )

        # ----- agents_current -----
        cols2 = db.execute("PRAGMA table_info(agents_current)").fetchall()
        if not cols2:
            db.execute("""
              CREATE TABLE agents_current (
                id          INTEGER PRIMARY KEY CHECK (id = 1),
                agent_role  TEXT,
                agent_id    TEXT,
                repo_url    TEXT
              );
            """)
        else:
            names2 = [c["name"] for c in cols2]
            if "repo_url" not in names2:
                db.execute(
                  "ALTER TABLE agents_current ADD COLUMN repo_url TEXT DEFAULT '';"
                )

        db.commit()

# Run migrations as soon as this module is imported
initialize_agents_db()


def generate_agent_id(agent_role: str, repo_url: str) -> str:
    """
    Return the next numeric agent_id (zero‐padded) for this role+repo.
    """
    with get_db() as db:
        rows = db.execute(
            "SELECT agent_id FROM agents_running "
            "WHERE agent_role = ? AND repo_url = ? ORDER BY id",
            (agent_role, repo_url)
        ).fetchall()
    existing = [int(r["agent_id"]) for r in rows if r["agent_id"].isdigit()]
    next_id = max(existing) + 1 if existing else 1
    return f"{next_id:03d}"


def list_running_agents(repo_url: str) -> List[dict]:
    """
    Return all running agents for the given repo_url.
    """
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM agents_running WHERE repo_url = ? ORDER BY created_at",
            (repo_url,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_running_agent(agent_role: str, repo_url: str) -> dict:
    """
    Create and return a new running‐agent row, auto‐generating agent_id.
    """
    agent_id = generate_agent_id(agent_role, repo_url)
    with get_db() as db:
        db.execute(
            "INSERT INTO agents_running (agent_role, agent_id, repo_url) VALUES (?,?,?)",
            (agent_role, agent_id, repo_url)
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM agents_running "
            "WHERE agent_role = ? AND agent_id = ? AND repo_url = ?",
            (agent_role, agent_id, repo_url)
        ).fetchone()
    return dict(row)


def remove_running_agent(agent_role: str, agent_id: str, repo_url: str) -> int:
    """
    Delete the specified running‐agent row. Returns num rows deleted (0 or 1).
    """
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM agents_running "
            "WHERE agent_role = ? AND agent_id = ? AND repo_url = ?",
            (agent_role, agent_id, repo_url)
        )
        db.commit()
    return cur.rowcount


def load_current_agent_pointer() -> Optional[Tuple[str, str, str]]:
    """
    Fetch the singleton current‐agent pointer as (agent_role, agent_id, repo_url), or None.
    """
    with get_db() as db:
        row = db.execute(
            "SELECT agent_role, agent_id, repo_url FROM agents_current WHERE id = 1"
        ).fetchone()
    if row and row["agent_role"] and row["agent_id"] and row["repo_url"]:
        return (row["agent_role"], row["agent_id"], row["repo_url"])
    return None


def save_current_agent_pointer(agent_role: str, agent_id: str, repo_url: str) -> None:
    """
    Upsert the singleton current‐agent pointer.
    """
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO agents_current "
            "(id, agent_role, agent_id, repo_url) VALUES (1,?,?,?)",
            (agent_role, agent_id, repo_url)
        )
        db.commit()


def delete_current_agent_pointer() -> None:
    """
    Clear the singleton current‐agent pointer.
    """
    with get_db() as db:
        db.execute("DELETE FROM agents_current WHERE id = 1")
        db.commit()


def clear_agents_for_repo(repo_url: str) -> None:
    """
    Delete all running agents and any current pointer for the given repo.
    """
    with get_db() as db:
        db.execute("DELETE FROM agents_running WHERE repo_url = ?", (repo_url,))
        db.execute("DELETE FROM agents_current WHERE repo_url = ?", (repo_url,))
        db.commit()


def list_all_repo_urls() -> List[str]:
    """
    Return every distinct repo_url for which we've ever created a running-agent.
    """
    with get_db() as db:
        rows = db.execute(
            "SELECT DISTINCT repo_url FROM agents_running"
        ).fetchall()
    return [r["repo_url"] for r in rows]
