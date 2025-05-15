# routers/router_info.py

import os
import json
import sqlite3
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from modules.routers_core import get_db_readonly_connection, object_to_dict, REPOS_DIR
from modules.routers_schema import Repo, BulkRepoInfoRequest

router = APIRouter(prefix="/repos", tags=["Repos"])


@router.get("/list", response_model=List[Repo])
def list_repos() -> List[Dict[str, Any]]:
    """
    List all admitted repositories (basic info only).
    Ordered by priority descending, then repo_url ascending.
    """
    conn = get_db_readonly_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
              r.repo_url,
              r.repo_name,
              r.repo_owner,
              r.team_id,
              r.default_branch,
              r.priority,
              r.jdk_version,
              m.source_file_count,
              m.total_loc,
              m.language,
              m.metadata
            FROM repositories AS r
            LEFT JOIN repos_metadata AS m
              ON r.repo_url = m.repo_url
            ORDER BY r.priority DESC, r.repo_url ASC
        """)
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        conn.close()
        raise HTTPException(status_code=503, detail="Database is busy, please retry later")
    finally:
        conn.close()

    result: List[Dict[str, Any]] = []
    for row in rows:
        # parse the remaining JSON blob
        try:
            md = json.loads(row["metadata"] or "{}")
        except Exception:
            md = {}
        dto = Repo(
            repo_url           = row["repo_url"],
            repo_name          = row["repo_name"],
            repo_owner         = row["repo_owner"],
            team_id            = row["team_id"],
            default_branch     = row["default_branch"],
            priority           = row["priority"],
            jdk_version        = row["jdk_version"],
            source_file_count  = row["source_file_count"] or 0,
            total_loc          = row["total_loc"] or 0,
            language           = row["language"],
            metadata           = md,
            repo_path          = os.path.join(REPOS_DIR, row["repo_name"]),
        )
        result.append(object_to_dict(dto))
    return result


@router.get("/info", response_model=Repo)
def get_repo_info(
    repo_url: str = Query(..., description="The URL of the repository")
) -> Dict[str, Any]:
    """
    Get detailed info for a single repo, including status, timestamps,
    metadata, and local path.
    """
    conn = get_db_readonly_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
              r.repo_url,
              r.repo_name,
              r.repo_owner,
              r.team_id,
              r.default_branch,
              r.priority,
              r.status,
              r.claimed_at,
              r.claim_ttl,
              r.jdk_version,
              m.source_file_count,
              m.total_loc,
              m.language,
              m.metadata
            FROM repositories AS r
            LEFT JOIN repos_metadata AS m
              ON r.repo_url = m.repo_url
            WHERE r.repo_url = ?
        """, (repo_url,))
        row = cur.fetchone()
    except sqlite3.OperationalError:
        conn.close()
        raise HTTPException(status_code=503, detail="Database is busy, please retry later")
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Repository not found.")

    # parse the remaining JSON blob
    try:
        md = json.loads(row["metadata"] or "{}")
    except Exception:
        md = {}

    dto = Repo(
        repo_url           = row["repo_url"],
        repo_name          = row["repo_name"],
        repo_owner         = row["repo_owner"],
        team_id            = row["team_id"],
        default_branch     = row["default_branch"],
        priority           = row["priority"],
        jdk_version        = row["jdk_version"],
        source_file_count  = row["source_file_count"] or 0,
        total_loc          = row["total_loc"] or 0,
        language           = row["language"],
        metadata           = md,
        repo_path          = os.path.join(REPOS_DIR, row["repo_name"]),
    )
    # include status/timestamps which Repo model may not have—attach directly
    out = object_to_dict(dto)
    out.update({
        "status":     row["status"],
        "claimed_at": row["claimed_at"],
        "claim_ttl":  row["claim_ttl"],
    })
    return out


@router.post("/info_bulk")
def info_bulk(request: BulkRepoInfoRequest) -> List[Dict[str, Any]]:
    """
    Bulk info lookup: returns per-repo detail or error.
    """
    results: List[Dict[str, Any]] = []
    for url in request.repo_urls:
        try:
            detail = get_repo_info(repo_url=url)
            results.append({
                "repo_url": url,
                "status":   "ok",
                "detail":   detail,
            })
        except HTTPException as he:
            results.append({
                "repo_url": url,
                "status":   "error",
                "detail":   he.detail,
            })
    return results
