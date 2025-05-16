# modules/db_agents.py

"""
Database‐level helpers for managing running agents, the singleton “current” pointer,
and a persistent call‐stack (with explicit parent links), all scoped by (repo_url).
"""

import sqlite3
from typing import List, Optional, Tuple, Dict

from modules.db import get_db


def initialize_agents_db():
    """
    Create or migrate the agents_running, agents_current, and agent_call_stack tables.
    (No in-place ALTER for parent columns—you must start with a fresh DB or manage migration separately.)
    """
    with get_db() as db:
        # 1) agents_running
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
                db.execute("ALTER TABLE agents_running ADD COLUMN repo_url TEXT NOT NULL DEFAULT '';")

        # 2) agents_current
        cols2 = db.execute("PRAGMA table_info(agents_current)").fetchall()
        if not cols2:
            db.execute("""
            CREATE TABLE agents_current (
                id          INTEGER PRIMARY KEY CHECK (id = 1),
                agent_role  TEXT    NOT NULL,
                agent_id    TEXT    NOT NULL,
                repo_url    TEXT    NOT NULL
            );
            """)
        else:
            names2 = [c["name"] for c in cols2]
            if "repo_url" not in names2:
                db.execute("ALTER TABLE agents_current ADD COLUMN repo_url TEXT NOT NULL DEFAULT '';")

        # 3) agent_call_stack (now with explicit parent pointers)
        cols3 = db.execute("PRAGMA table_info(agent_call_stack)").fetchall()
        if not cols3:
            db.execute("""
            CREATE TABLE agent_call_stack (
                repo_url    TEXT    NOT NULL,
                stack_idx   INTEGER NOT NULL,
                agent_role  TEXT    NOT NULL,
                agent_id    TEXT    NOT NULL,
                parent_role TEXT,               -- new
                parent_id   TEXT,               -- new
                pushed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(repo_url,stack_idx)
            );
            """)

# Run migrations (or creations) at import time
initialize_agents_db()


def generate_agent_id(
    agent_role: str,
    repo_url:   str
) -> str:
    """
    Return the next numeric agent_id (zero‐padded) for this role+repo.
    """
    with get_db() as db:
        rows = db.execute(
            "SELECT agent_id FROM agents_running "
            "WHERE agent_role=? AND repo_url=? ORDER BY id",
            (agent_role, repo_url)
        ).fetchall()

    existing = [int(r["agent_id"]) for r in rows if r["agent_id"].isdigit()]
    next_id = max(existing) + 1 if existing else 1
    return f"{next_id:03d}"


def list_running_agents(
    repo_url:  str
) -> List[Dict]:
    """
    Return all running agents for the given repo_url.
    """
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM agents_running WHERE repo_url=? ORDER BY created_at",
            (repo_url,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_running_agent(
    agent_role: str,
    repo_url:   str,
    agent_id:   Optional[str] = None,
) -> Dict:
    """
    Create and return a new running-agent row.
    If agent_id is provided, INSERT with that ID;
    otherwise auto-generate a fresh numeric ID.
    """
    aid = agent_id if agent_id is not None else generate_agent_id(agent_role, repo_url)

    with get_db() as db:
        db.execute(
            "INSERT INTO agents_running (agent_role,agent_id,repo_url) VALUES (?,?,?)",
            (agent_role, aid, repo_url)
        )
        row = db.execute(
            "SELECT * FROM agents_running "
            "WHERE agent_role=? AND agent_id=? AND repo_url=?",
            (agent_role, aid, repo_url)
        ).fetchone()

    return dict(row)


def remove_running_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   str
) -> int:
    """
    Delete a running-agent row. Returns number of rows deleted.
    """
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM agents_running "
            "WHERE agent_role=? AND agent_id=? AND repo_url=?",
            (agent_role, agent_id, repo_url)
        )
    return cur.rowcount


def clear_agents_for_repo(
    repo_url:  str
) -> None:
    """
    Delete all running agents and the current pointer for the given repo.
    """
    with get_db() as db:
        db.execute("DELETE FROM agents_running WHERE repo_url=?", (repo_url,))
        db.execute("DELETE FROM agents_current  WHERE repo_url=?", (repo_url,))


def load_current_agent_pointer() -> Optional[Tuple[str,str,str]]:
    """
    Fetch the singleton current-agent pointer as (agent_role,agent_id,repo_url), or None.
    """
    with get_db() as db:
        row = db.execute(
            "SELECT agent_role, agent_id, repo_url FROM agents_current WHERE id=1"
        ).fetchone()
    if row:
        return (row["agent_role"], row["agent_id"], row["repo_url"])
    return None


def save_current_agent_pointer(
    agent_role: str,
    agent_id:   str,
    repo_url:   str
) -> None:
    """
    Upsert the singleton current-agent pointer.
    """
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO agents_current "
            "(id,agent_role,agent_id,repo_url) VALUES (1,?,?,?)",
            (agent_role, agent_id, repo_url)
        )


def delete_current_agent_pointer() -> None:
    """
    Clear the singleton current-agent pointer.
    """
    with get_db() as db:
        db.execute("DELETE FROM agents_current WHERE id=1")


# ----------------------------------------------------------------
# Persistent call-stack: push, pop, and load operations
# ----------------------------------------------------------------

def push_call_stack(
    repo_url:   str,
    agent_role: str,
    agent_id:   str
) -> None:
    """
    Push a new entry onto the persistent call-stack for (repo_url),
    recording an explicit parent_role/parent_id.
    """
    with get_db() as db:
        # find current top index
        mx_row = db.execute(
            "SELECT MAX(stack_idx) AS mx FROM agent_call_stack WHERE repo_url=?",
            (repo_url,)
        ).fetchone()
        mx = mx_row["mx"]
        next_idx = (mx + 1) if mx is not None else 0

        # look up parent if present
        if mx is not None:
            top = db.execute(
                "SELECT agent_role, agent_id FROM agent_call_stack "
                "WHERE repo_url=? AND stack_idx=?",
                (repo_url, mx)
            ).fetchone()
            parent_role, parent_id = top["agent_role"], top["agent_id"]
        else:
            parent_role = None
            parent_id   = None

        # insert with parent pointers
        db.execute(
            """
            INSERT INTO agent_call_stack
              (repo_url, stack_idx, agent_role, agent_id, parent_role, parent_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (repo_url, next_idx, agent_role, agent_id, parent_role, parent_id)
        )


def pop_call_stack(
    repo_url:  str
) -> Optional[Tuple[str,str]]:
    """
    Pop the top entry from the persistent call-stack and return (agent_role,agent_id),
    or None if the stack was empty.
    """
    with get_db() as db:
        row = db.execute(
            "SELECT MAX(stack_idx) AS mx FROM agent_call_stack WHERE repo_url=?",
            (repo_url,)
        ).fetchone()
        mx = row["mx"]
        if mx is None:
            return None

        top = db.execute(
            "SELECT agent_role, agent_id FROM agent_call_stack "
            "WHERE repo_url=? AND stack_idx=?",
            (repo_url, mx)
        ).fetchone()

        db.execute(
            "DELETE FROM agent_call_stack WHERE repo_url=? AND stack_idx=?",
            (repo_url, mx)
        )

    return (top["agent_role"], top["agent_id"])


def load_call_stack(
    repo_url:  str
) -> List[Tuple[str,str,Optional[str],Optional[str]]]:
    """
    Load the entire persistent call-stack for (repo_url) in order
    from bottom (0) to top, returning tuples of
      (agent_role, agent_id, parent_role, parent_id).
    """
    with get_db() as db:
        rows = db.execute(
            """
            SELECT agent_role, agent_id, parent_role, parent_id
              FROM agent_call_stack
             WHERE repo_url=?
             ORDER BY stack_idx
            """,
            (repo_url,)
        ).fetchall()

    return [
        (r["agent_role"], r["agent_id"], r["parent_role"], r["parent_id"])
        for r in rows
    ]
