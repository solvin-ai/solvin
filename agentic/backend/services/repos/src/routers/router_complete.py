# routers/router_complete.py

from fastapi import APIRouter, HTTPException, Depends
import sqlite3

from modules.routers_core import get_db_write, execute_with_retry
from modules.routers_schema import RepoCompleteRequest, BulkRepoCompleteRequest

router = APIRouter(
    prefix="/repos",
    tags=["Repos"],
)

@router.post("/complete")
def complete_repo(
    request: RepoCompleteRequest,
    conn: sqlite3.Connection = Depends(get_db_write),
):
    """
    Mark a claimed repository as complete by updating its status.
    Only succeeds if status == 'claimed'.
    """
    cur = conn.cursor()
    try:
        execute_with_retry(
            cur,
            """
            UPDATE repositories
               SET status     = 'completed',
                   claimed_at = NULL,
                   claim_ttl  = NULL
             WHERE repo_url = ? AND status = 'claimed'
            """,
            (request.repo_url,)
        )
    except sqlite3.OperationalError as e:
        # still locked after retries
        raise HTTPException(status_code=503, detail="Database busy, try again") from e

    if cur.rowcount == 0:
        # either it doesn't exist or isn't in 'claimed' status
        raise HTTPException(
            status_code=404,
            detail="Repository not found or not in 'claimed' status."
        )

    return {
        "message": f"Repository '{request.repo_url}' marked as completed."
    }


@router.post("/complete_bulk")
def complete_bulk(
    request: BulkRepoCompleteRequest,
    conn: sqlite3.Connection = Depends(get_db_write),
):
    """
    Bulk-complete multiple claimed repositories.
    Returns per-repo status and detail.
    """
    results = []
    cur = conn.cursor()

    for repo in request.repos:
        try:
            execute_with_retry(
                cur,
                """
                UPDATE repositories
                   SET status     = 'completed',
                       claimed_at = NULL,
                       claim_ttl  = NULL
                 WHERE repo_url = ? AND status = 'claimed'
                """,
                (repo.repo_url,)
            )
            if cur.rowcount == 0:
                # not found or wrong status
                raise HTTPException(status_code=404, detail="Repository not found or not in 'claimed' status.")
            results.append({
                "repo_url": repo.repo_url,
                "status":    "ok",
                "detail":    {"message": "completed"}
            })
        except HTTPException as he:
            results.append({
                "repo_url": repo.repo_url,
                "status":    "error",
                "detail":    he.detail
            })
        except sqlite3.OperationalError:
            results.append({
                "repo_url": repo.repo_url,
                "status":    "error",
                "detail":    "Database busy, try again"
            })

    return results
