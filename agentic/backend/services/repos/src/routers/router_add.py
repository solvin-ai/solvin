# routers/router_add.py

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
import sqlite3
import json
from typing import Dict, Any, List

from modules.routers_core import get_db_write, repo_queue, queued_repo_urls
from modules.routers_schema import RepoAddRequest, BulkRepoAddRequest

router = APIRouter(prefix="/repos", tags=["Repos"])


@router.post("/add")
async def add_repo(
    request: RepoAddRequest,
    conn: sqlite3.Connection = Depends(get_db_write),
) -> Dict[str, Any]:
    """
    Insert a repo + metadata.  Duplicate repo_url → 409 Conflict (returned, not raised).
    """
    cur = conn.cursor()
    try:
        # 1) Insert repository record
        cur.execute(
            """
            INSERT INTO repositories
              (repo_url, repo_name, repo_owner,
               customer_id, team_id, default_branch,
               status, priority, jdk_version)
            VALUES (?, ?, ?, ?, ?, ?, 'unclaimed', ?, ?)
            """,
            (
                request.repo_url,
                request.repo_name,
                request.repo_owner,
                request.customer_id,
                request.team_id,
                request.default_branch,
                request.priority,
                request.jdk_version,
            ),
        )
        # 2) Seed metadata, now with first‐class columns
        cur.execute(
            """
            INSERT INTO repos_metadata
              (repo_url, source_file_count, total_loc, language, metadata)
            VALUES (?, 0, 0, NULL, ?)
            """,
            (
                request.repo_url,
                json.dumps(request.metadata, ensure_ascii=False),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # PK conflict → already exists
        return JSONResponse(
            status_code=409,
            content={"detail": "Repository already exists"},
        )

    # 3) Enqueue for background claimant
    if request.repo_url not in queued_repo_urls:
        await repo_queue.put((
            -request.priority,
            request.repo_url,
            {
                "repo_url":   request.repo_url,
                "repo_owner": request.repo_owner,
                "team_id":    request.team_id,
                "priority":   request.priority,
            },
        ))
        queued_repo_urls.add(request.repo_url)

    # 4) Return success
    return {
        "message":        "Repository added",
        "repo_url":       request.repo_url,
        "repo_name":      request.repo_name,
        "repo_owner":     request.repo_owner,
        "team_id":        request.team_id,
        "default_branch": request.default_branch,
        # metadata stays in the JSON blob
        "metadata":       request.metadata,
    }


@router.post("/add_bulk")
async def add_bulk(
    request: BulkRepoAddRequest,
    conn: sqlite3.Connection = Depends(get_db_write),
) -> List[Dict[str, Any]]:
    """
    Bulk add: per-repo ok/error.  Duplicates → status=error in the response body.
    """
    results: List[Dict[str, Any]] = []
    cur = conn.cursor()

    for entry in request.repos:
        try:
            # 1) Insert repository record
            cur.execute(
                """
                INSERT INTO repositories
                  (repo_url, repo_name, repo_owner,
                   customer_id, team_id, default_branch,
                   status, priority, jdk_version)
                VALUES (?, ?, ?, ?, ?, ?, 'unclaimed', ?, ?)
                """,
                (
                    entry.repo_url,
                    entry.repo_name,
                    entry.repo_owner,
                    entry.customer_id,
                    entry.team_id,
                    entry.default_branch,
                    entry.priority,
                    entry.jdk_version,
                ),
            )
            # 2) Seed metadata
            cur.execute(
                """
                INSERT INTO repos_metadata
                  (repo_url, source_file_count, total_loc, language, metadata)
                VALUES (?, 0, 0, NULL, ?)
                """,
                (
                    entry.repo_url,
                    json.dumps(entry.metadata, ensure_ascii=False),
                ),
            )
            conn.commit()

            # 3) Enqueue
            if entry.repo_url not in queued_repo_urls:
                await repo_queue.put((
                    -entry.priority,
                    entry.repo_url,
                    {
                        "repo_url":   entry.repo_url,
                        "repo_owner": entry.repo_owner,
                        "team_id":    entry.team_id,
                        "priority":   entry.priority,
                    },
                ))
                queued_repo_urls.add(entry.repo_url)

            results.append({
                "repo_url": entry.repo_url,
                "status":   "ok",
                "detail": {
                    "message":        "Repository added",
                    "repo_url":       entry.repo_url,
                    "repo_name":      entry.repo_name,
                    "repo_owner":     entry.repo_owner,
                    "team_id":        entry.team_id,
                    "default_branch": entry.default_branch,
                    "metadata":       entry.metadata,
                },
            })

        except sqlite3.IntegrityError:
            results.append({
                "repo_url": entry.repo_url,
                "status":    "error",
                "detail":    "Repository already exists",
            })

    return results
