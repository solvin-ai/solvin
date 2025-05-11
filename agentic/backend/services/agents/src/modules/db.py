# modules/db.py

import os
import sqlite3
from contextlib import contextmanager
from shared.config import config

# The single SQLite file for all agents‐and‐turns data
DB_PATH = config["AGENTS_DB_FILE"]

def ensure_db_dir():
    """
    Make sure the directory for DB_PATH exists.
    """
    d = os.path.dirname(DB_PATH)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

@contextmanager
def get_db():
    """
    Context‐manager yielding a sqlite3.Connection with foreign‐keys ON,
    WAL mode, and a long busy timeout for concurrent test safety.
    Commits on exit, rolls back on exception.
    """
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")  # For WAL, NORMAL is safe and improves speed
    try:
        yield conn
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """
    Create or migrate all needed tables in the agents‐DB:
      • agents_running
      • agents_current
      • turns
      • tool_meta
      • messages
      • agent_state
    """
    with get_db() as db:
        # 1) agents_running
        db.execute("""
        CREATE TABLE IF NOT EXISTS agents_running (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_role   TEXT    NOT NULL,
            agent_id     TEXT    NOT NULL,
            repo_url    TEXT    NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2) agents_current
        db.execute("""
        CREATE TABLE IF NOT EXISTS agents_current (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            agent_role TEXT,
            agent_id   TEXT,
            repo_url  TEXT
        );
        """)

        # 3) turns
        db.execute("""
        CREATE TABLE IF NOT EXISTS turns (
            repo_url        TEXT    NOT NULL,
            agent_role       TEXT    NOT NULL,
            agent_id         TEXT    NOT NULL,
            turn_idx         INTEGER NOT NULL,
            total_char_count INTEGER NOT NULL,
            PRIMARY KEY(repo_url,agent_role,agent_id,turn_idx)
        );
        """)

        # 4) tool_meta
        db.execute("""
        CREATE TABLE IF NOT EXISTS tool_meta (
            repo_url            TEXT    NOT NULL,
            agent_role           TEXT    NOT NULL,
            agent_id             TEXT    NOT NULL,
            turn_idx             INTEGER NOT NULL,
            tool_name            TEXT,
            execution_time       REAL,
            pending_deletion     INTEGER NOT NULL CHECK(pending_deletion IN (0,1)),
            deleted              INTEGER NOT NULL CHECK(deleted IN (0,1)),
            rejection            TEXT,
            status               TEXT,
            args_hash            TEXT,
            preservation_policy  TEXT,
            normalized_args_json TEXT    NOT NULL,
            normalized_filename  TEXT,
            input_args_json      TEXT    NOT NULL,
            PRIMARY KEY(repo_url,agent_role,agent_id,turn_idx),
            FOREIGN KEY(repo_url,agent_role,agent_id,turn_idx)
              REFERENCES turns(repo_url,agent_role,agent_id,turn_idx)
              ON DELETE CASCADE
        );
        """)

        # 5) messages
        db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            repo_url           TEXT    NOT NULL,
            agent_role          TEXT    NOT NULL,
            agent_id            TEXT    NOT NULL,
            turn_idx            INTEGER NOT NULL,
            message_idx         INTEGER NOT NULL,
            role                TEXT    NOT NULL,
            content             TEXT    NOT NULL,
            timestamp           TEXT    NOT NULL,
            original_message_id INTEGER NOT NULL,
            char_count          INTEGER NOT NULL,
            raw_json            TEXT,
            PRIMARY KEY(repo_url,agent_role,agent_id,turn_idx,message_idx),
            FOREIGN KEY(repo_url,agent_role,agent_id,turn_idx)
              REFERENCES turns(repo_url,agent_role,agent_id,turn_idx)
              ON DELETE CASCADE
        );
        """)

        # 6) agent_state
        db.execute("""
        CREATE TABLE IF NOT EXISTS agent_state (
            repo_url         TEXT    NOT NULL,
            agent_role        TEXT    NOT NULL,
            agent_id          TEXT    NOT NULL,
            last_turn_idx     INTEGER NOT NULL DEFAULT -1,
            last_message_id   INTEGER NOT NULL DEFAULT -1,
            PRIMARY KEY(repo_url,agent_role,agent_id)
        );
        """)
