# routers/router_complete.py

from fastapi import APIRouter, HTTPException, status, Depends
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
    Idempotent: if already completed, returns 200 with a message.
    """
    cur = conn.cursor()

    # First, try to transition from 'claimed' → 'completed'
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
        raise HTTPException(status_code=503, detail="Database busy, try again") from e

    # If we actually updated a row, great
    if cur.rowcount > 0:
        conn.commit()
        return {"message": f"Repository '{request.repo_url}' marked as completed."}

    # No rows updated → either doesn't exist, or is already completed, or is unclaimed
    cur.execute(
        "SELECT status FROM repositories WHERE repo_url = ?",
        (request.repo_url,)
    )
    row = cur.fetchone()
    if not row:
        # never existed
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found."
        )

    current = row["status"]
    if current == "completed":
        # idempotent success
        return {"message": f"Repository '{request.repo_url}' is already completed."}

    # must be 'unclaimed' or something else
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Cannot complete repository in status '{current}'."
    )


@router.post("/complete_bulk")
def complete_bulk(
    request: BulkRepoCompleteRequest,
    conn: sqlite3.Connection = Depends(get_db_write),
):
    """
    Bulk-complete multiple claimed repositories.
    Idempotent on already-completed; differentiates not-found vs wrong-status.
    """
    results = []
    cur = conn.cursor()

    for repo in request.repos:
        url = repo.repo_url
        try:
            # try to mark claimed → completed
            execute_with_retry(
                cur,
                """
                UPDATE repositories
                   SET status     = 'completed',
                       claimed_at = NULL,
                       claim_ttl  = NULL
                 WHERE repo_url = ? AND status = 'claimed'
                """,
                (url,)
            )
            if cur.rowcount > 0:
                results.append({
                    "repo_url": url,
                    "status":    "ok",
                    "detail":    {"message": "completed"}
                })
                continue

            # nothing updated → inspect current status
            cur.execute(
                "SELECT status FROM repositories WHERE repo_url = ?",
                (url,)
            )
            row = cur.fetchone()
            if not row:
                results.append({
                    "repo_url": url,
                    "status":    "error",
                    "detail":    "not found"
                })
            elif row["status"] == "completed":
                # idempotent success
                results.append({
                    "repo_url": url,
                    "status":    "ok",
                    "detail":    {"message": "already completed"}
                })
            else:
                results.append({
                    "repo_url": url,
                    "status":    "error",
                    "detail":    f"cannot complete from status '{row['status']}'"
                })

        except sqlite3.OperationalError:
            results.append({
                "repo_url": url,
                "status":    "error",
                "detail":    "database busy, try again"
            })

    # only commit once at the end if anything changed
    conn.commit()
    return results
