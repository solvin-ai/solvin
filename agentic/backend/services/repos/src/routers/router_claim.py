# routers/router_claim.py

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import PlainTextResponse
import time
import sqlite3
import asyncio

from modules.routers_core import get_db_write, object_to_dict
from modules.routers_schema import RepoClaimResponse

router = APIRouter(prefix="/repos", tags=["Repos"])


@router.post("/claim", response_model=RepoClaimResponse)
async def claim_repo(
    ttl: int = Query(60, description="Time-to-live in seconds"),
    conn: sqlite3.Connection = Depends(get_db_write),
):
    """
    Claim the next available repo (non-blocking). 404 if none.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT repo_url
          FROM repositories
         WHERE status = 'unclaimed'
      ORDER BY priority DESC, repo_url ASC
         LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No available repository to claim.")

    repo_url = row["repo_url"]
    now = time.time()
    cur.execute("""
        UPDATE repositories
           SET status     = 'claimed',
               claimed_at = ?,
               claim_ttl  = ?
         WHERE repo_url = ? AND status = 'unclaimed'
    """, (now, ttl, repo_url))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Repository already claimed or not found.")

    # Re-fetch only the minimal five fields
    cur.execute("""
        SELECT
            repo_url,
            repo_owner,
            repo_name,
            default_branch,
            priority
          FROM repositories
         WHERE repo_url = ?
    """, (repo_url,))
    rec = cur.fetchone()
    if not rec:
        raise HTTPException(status_code=500, detail="Repository not found after claiming.")

    conn.commit()

    # coalesce default_branch to empty string if NULL
    default_branch = rec["default_branch"] or ""

    resp = RepoClaimResponse(
        repo_url       = rec["repo_url"],
        repo_owner     = rec["repo_owner"],
        repo_name      = rec["repo_name"],
        default_branch = default_branch,
        priority       = rec["priority"],
    )
    return object_to_dict(resp)


@router.post("/claim_blocking", response_model=RepoClaimResponse)
async def claim_blocking(
    timeout: float = Query(5.0, description="Max wait time in seconds"),
    conn: sqlite3.Connection = Depends(get_db_write),
):
    """
    Wait up to `timeout` seconds for an unclaimed repo, then claim it.
    404 if timed out.
    """
    start = time.time()
    while True:
        cur = conn.cursor()
        cur.execute("""
            SELECT repo_url
              FROM repositories
             WHERE status = 'unclaimed'
          ORDER BY priority DESC, repo_url ASC
             LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            repo_url = row["repo_url"]
            now = time.time()
            cur.execute("""
                UPDATE repositories
                   SET status     = 'claimed',
                       claimed_at = ?,
                       claim_ttl  = ?
                 WHERE repo_url = ? AND status = 'unclaimed'
            """, (now, int(timeout), repo_url))
            if cur.rowcount > 0:
                cur.execute("""
                    SELECT
                        repo_url,
                        repo_owner,
                        repo_name,
                        default_branch,
                        priority
                      FROM repositories
                     WHERE repo_url = ?
                """, (repo_url,))
                rec = cur.fetchone()
                if rec:
                    conn.commit()

                    default_branch = rec["default_branch"] or ""

                    resp = RepoClaimResponse(
                        repo_url       = rec["repo_url"],
                        repo_owner     = rec["repo_owner"],
                        repo_name      = rec["repo_name"],
                        default_branch = default_branch,
                        priority       = rec["priority"],
                    )
                    return object_to_dict(resp)

        # timed out?
        if time.time() - start >= timeout:
            return PlainTextResponse(
                content=f"No available repository to claim after {timeout:.1f} seconds.",
                status_code=404,
            )

        await asyncio.sleep(0.1)
