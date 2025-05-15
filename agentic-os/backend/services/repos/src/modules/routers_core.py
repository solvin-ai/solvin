# modules/routers_core.py

import os
import sqlite3
import time
import asyncio
import dataclasses
import ast

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from shared.config import config
from shared.logger import logger

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
REPOS_DB_FILE              = config["REPOS_DB_FILE"]
REPOS_DIR                  = config.get("REPOS_DIR", "./repos")
QUEUE_REFRESH_INTERVAL_SEC = float(config.get("QUEUE_REFRESH_INTERVAL_SEC", 3.0))
QUEUE_MIN_QUEUE_SIZE       = int(config["QUEUE_MIN_QUEUE_SIZE"])
QUEUE_BATCH_SIZE           = int(config["QUEUE_BATCH_SIZE"])
QUEUE_TIMEOUT_SEC          = float(config.get("QUEUE_TIMEOUT_SEC", 5.0))
REPO_CLAIM_TTL_SEC         = float(config.get("REPO_CLAIM_TTL_SEC", 5.0))

# -----------------------------------------------------------------------------
# Helper: retry only on SQLITE_BUSY (“database is locked”) with debug logs
# -----------------------------------------------------------------------------
def execute_with_retry(
    cur: sqlite3.Cursor,
    sql: str,
    params: tuple = (),
    retries: int = 2,
    backoff: float = 0.01
) -> sqlite3.Cursor:
    for attempt in range(1, retries + 1):
        try:
            return sqlite3.Cursor.execute(cur, sql, params)
        except sqlite3.OperationalError as e:
            txt = str(e).lower()
            if "locked" in txt or "busy" in txt:
                logger.debug(
                    f"execute_with_retry: SQLITE_BUSY on attempt {attempt}/{retries}, "
                    f"sql={sql!r}, params={params!r}"
                )
                time.sleep(backoff)
                continue
            raise
    # Final attempt
    return sqlite3.Cursor.execute(cur, sql, params)


# -----------------------------------------------------------------------------
# Cursor & Connection classes that retry on SQLITE_BUSY
# and open WAL mode
# -----------------------------------------------------------------------------
class RetryingCursor(sqlite3.Cursor):
    def execute(self, sql, params=()):
        return execute_with_retry(self, sql, params)

    def executemany(self, sql, seq_of_params):
        return super().executemany(sql, seq_of_params)


class RetryingConnection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.row_factory = sqlite3.Row
        # WAL + reasonable sync + foreign keys
        super().execute("PRAGMA journal_mode = WAL;")
        super().execute("PRAGMA busy_timeout = 5000;")
        super().execute("PRAGMA synchronous = NORMAL;")
        super().execute("PRAGMA foreign_keys = ON;")

    def cursor(self, factory=RetryingCursor):
        return super().cursor(factory)

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, seq_of_params):
        return self.cursor().executemany(sql, seq_of_params)


# -----------------------------------------------------------------------------
# Connection factories
# -----------------------------------------------------------------------------
def get_db_connection() -> sqlite3.Connection:
    """
    Writable connection: WAL mode, retries on busy, up to 5s, autocommit off.
    """
    return sqlite3.connect(
        REPOS_DB_FILE,
        timeout=5.0,
        check_same_thread=False,
        isolation_level=None,
        factory=RetryingConnection
    )


def get_db_readonly_connection() -> sqlite3.Connection:
    """
    Read‐only connection: WAL + dirty reads (read_uncommitted=1), non‐blocking.
    """
    # timeout=0 → do not wait if locked; read_uncommitted=1 → dirty reads
    conn = sqlite3.connect(
        REPOS_DB_FILE,
        timeout=0.0,
        check_same_thread=False,
        isolation_level=None
    )
    conn.row_factory = sqlite3.Row
    for stmt in (
        "PRAGMA journal_mode = WAL;",
        "PRAGMA read_uncommitted = 1;",
        "PRAGMA busy_timeout = 0;",
        "PRAGMA foreign_keys = ON;",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            logger.debug(f"Read-only PRAGMA failed ({stmt.strip()}): {e!r}")
    return conn


# -----------------------------------------------------------------------------
# FastAPI dependencies
# -----------------------------------------------------------------------------
def get_db_read():
    conn = get_db_readonly_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_db_write():
    """
    Writable DB dependency: no in‐process lock, rely on SQLite's WAL + busy_timeout.
    """
    conn = get_db_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except:
            pass


# -----------------------------------------------------------------------------
# Schema init (repositories + separate metadata table)
# -----------------------------------------------------------------------------
def init_db() -> None:
    if REPOS_DB_FILE != ":memory:":
        try:
            os.remove(REPOS_DB_FILE)
        except FileNotFoundError:
            pass
        parent = os.path.dirname(REPOS_DB_FILE)
        if parent:
            os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(REPOS_DB_FILE)
    cur  = conn.cursor()

    cur.execute("""
      CREATE TABLE IF NOT EXISTS repositories (
        repo_url        TEXT    PRIMARY KEY,
        repo_name       TEXT              NOT NULL,
        repo_owner      TEXT              NOT NULL,
        customer_id     TEXT              NULL,
        team_id         TEXT              NOT NULL,
        default_branch  TEXT              NULL,
        status          TEXT    DEFAULT 'unclaimed',
        priority        INTEGER DEFAULT 0,
        claimed_at      REAL              NULL,
        claim_ttl       INTEGER           NULL,
        jdk_version     TEXT              NULL
      )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_repos_unclaimed ON repositories(status, priority DESC, repo_url ASC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_repos_status ON repositories(status)")
    cur.execute("""
      CREATE TABLE IF NOT EXISTS repos_metadata (
        repo_url            TEXT    NOT NULL
          REFERENCES repositories(repo_url) ON DELETE CASCADE,
        source_file_count   INTEGER DEFAULT 0,
        total_loc           INTEGER DEFAULT 0,
        language            TEXT    NULL,
        metadata            TEXT    NOT NULL,
        PRIMARY KEY(repo_url)
      )
    """)
    conn.commit()
    conn.close()


# -----------------------------------------------------------------------------
# Background queue refresher
# -----------------------------------------------------------------------------
repo_queue       = asyncio.PriorityQueue()
queued_repo_urls = set()

async def refresh_repo_queue() -> None:
    while True:
        try:
            if repo_queue.qsize() < QUEUE_MIN_QUEUE_SIZE:
                try:
                    conn = get_db_readonly_connection()
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not open read-only DB (busy?): {e!r}")
                    await asyncio.sleep(QUEUE_REFRESH_INTERVAL_SEC)
                    continue

                cur = conn.cursor()
                try:
                    cur.execute("""
                      SELECT repo_url, repo_owner, team_id, priority
                        FROM repositories
                       WHERE status = 'unclaimed'
                    ORDER BY priority DESC, repo_url ASC
                       LIMIT ?
                    """, (QUEUE_BATCH_SIZE,))
                    rows = cur.fetchall()
                except sqlite3.OperationalError:
                    rows = []
                finally:
                    conn.close()

                for r in rows:
                    url = r["repo_url"]
                    if url not in queued_repo_urls:
                        await repo_queue.put((
                            -r["priority"],
                            url,
                            {
                                "repo_url":   r["repo_url"],
                                "repo_owner": r["repo_owner"],
                                "team_id":    r["team_id"],
                                "priority":   r["priority"],
                            }
                        ))
                        queued_repo_urls.add(url)
            await asyncio.sleep(QUEUE_REFRESH_INTERVAL_SEC)
        except Exception:
            logger.exception("Unexpected error in refresh_repo_queue")
            await asyncio.sleep(QUEUE_REFRESH_INTERVAL_SEC)


# -----------------------------------------------------------------------------
# Background task to un-claim expired TTLs
# -----------------------------------------------------------------------------
async def unclaim_expired_task() -> None:
    while True:
        await asyncio.sleep(REPO_CLAIM_TTL_SEC)
        now = time.time()
        conn = None
        try:
            conn = get_db_connection()
            cur  = conn.cursor()
            cur.execute("""
              SELECT repo_url, priority
                FROM repositories
               WHERE status = 'claimed'
                 AND claimed_at + claim_ttl <= ?
            """, (now,))
            expired = cur.fetchall()
            for row in expired:
                url = row["repo_url"]
                pr  = row["priority"]
                cur.execute("""
                  UPDATE repositories
                     SET status     = 'unclaimed',
                         claimed_at = NULL,
                         claim_ttl  = NULL
                   WHERE repo_url = ?
                """, (url,))
                if url not in queued_repo_urls:
                    await repo_queue.put((
                        -pr,
                        url,
                        {
                            "repo_url":   url,
                            "repo_owner": None,
                            "team_id":    None,
                            "priority":   pr,
                        }
                    ))
                    queued_repo_urls.add(url)
            conn.commit()
        except Exception:
            logger.exception("Error in unclaim_expired_task")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass


# -----------------------------------------------------------------------------
# Utility: convert Pydantic/dataclass → dict
# -----------------------------------------------------------------------------
def object_to_dict(obj):
    if isinstance(obj, dict):
        return obj
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return {"as_str": str(obj)}


# -----------------------------------------------------------------------------
# Admission jobs loader
# -----------------------------------------------------------------------------
def get_admission_jobs():
    raw = config.get("ADMISSION_ORDERED_TASKS", ["clone_repo","detect_language","code_stats"])
    if isinstance(raw, str):
        try:
            lst = ast.literal_eval(raw)
            if isinstance(lst, list) and all(isinstance(x, str) for x in lst):
                return lst
        except Exception:
            pass
        logger.warning("ADMISSION_ORDERED_TASKS invalid, using default")
    elif isinstance(raw, list):
        return raw
    return ["clone_repo","detect_language","code_stats"]


# -----------------------------------------------------------------------------
# Register a 503 handler for sqlite3.OperationalError("database is locked")
# -----------------------------------------------------------------------------
def register_sqlite_busy_handler(app):
    @app.exception_handler(sqlite3.OperationalError)
    async def _sqlite_busy_handler(request: Request, exc: sqlite3.OperationalError):
        txt = str(exc).lower()
        if "locked" in txt or "busy" in txt:
            logger.warning(f"SQLite busy/locked → returning 503: {exc!r}")
            return JSONResponse(
                status_code=503,
                content={"detail": "Database is busy, please retry later"}
            )
        raise exc
