# routers/router_admit.py

from fastapi import APIRouter, HTTPException, Depends
import os
import json
import sqlite3

from modules.routers_core import (
    get_db_write,
    REPOS_DIR,
    repo_queue,
    queued_repo_urls,
    get_admission_tasks,
)
from admission import run_admission_pipeline
from modules.routers_schema import RepoAdmitByUrlRequest, BulkRepoAdmitByUrlRequest

router = APIRouter(prefix="/repos", tags=["Repos"])


@router.post("/admit")
async def admit_repo(
    request: RepoAdmitByUrlRequest,
    conn: sqlite3.Connection = Depends(get_db_write),
):
    """
    Insert into DB, run admission‐task pipeline (clone, detect, stats),
    persist metadata, and enqueue for claiming.
    Duplicate repo_url → 409 Conflict.
    """
    # 1) Normalize URL → repo_name / repo_owner
    url        = request.repo_url.strip().rstrip("/")
    parts      = url.split("/")
    raw        = parts[-1]
    repo_name  = raw[:-4] if raw.endswith(".git") else raw
    repo_owner = parts[-2] if len(parts) >= 2 else ""
    # Path where tasks will clone/update the repo
    repo_path = os.path.join(REPOS_DIR, repo_name)

    cur = conn.cursor()
    try:
        # 2) Insert into repositories
        cur.execute(
            """
            INSERT INTO repositories
              (repo_url, repo_name, repo_owner,
               customer_id, team_id, default_branch,
               status, priority, jdk_version)
            VALUES (?, ?, ?, ?, ?, ?, 'unclaimed', ?, NULL)
            """,
            (
                url,
                repo_name,
                repo_owner,
                None,
                request.team_id,
                request.default_branch,
                request.priority,
            ),
        )
        # 3) Seed an empty metadata row (will overwrite shortly)
        cur.execute(
            """
            INSERT INTO repos_metadata
              (repo_url, source_file_count, total_loc, language, metadata)
            VALUES (?, 0, 0, NULL, ?)
            """,
            (url, json.dumps({}, ensure_ascii=False)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Repository already admitted")

    # 4) Build repo_info and run the admission pipeline
    repo_info = {
        "repo_url":       url,
        "repo_name":      repo_name,
        "repo_owner":     repo_owner,
        "team_id":        request.team_id,
        "default_branch": request.default_branch,
        "priority":       request.priority,
        "metadata":       {},              # start empty
    }
    task_list   = get_admission_tasks()
    updated_info = run_admission_pipeline(repo_path, repo_info, task_list)
    final_md     = updated_info.get("metadata", {})

    # 5) Extract first-class fields, leave rest in JSON
    sf_count  = final_md.pop("source_file_count", 0)
    total_loc = final_md.pop("total_loc", 0)
    lang      = final_md.pop("language", None)

    cur.execute(
        """
        UPDATE repos_metadata
           SET source_file_count = ?,
               total_loc         = ?,
               language          = ?,
               metadata          = ?
         WHERE repo_url = ?
        """,
        (
            sf_count,
            total_loc,
            lang,
            json.dumps(final_md, ensure_ascii=False),
            url,
        ),
    )
    conn.commit()

    # 6) Enqueue for the background claimant
    if url not in queued_repo_urls:
        await repo_queue.put((
            -request.priority,
            url,
            {
                "repo_url":   url,
                "repo_owner": repo_owner,
                "team_id":    request.team_id,
                "priority":   request.priority,
            },
        ))
        queued_repo_urls.add(url)

    # 7) Read back for response (include new columns)
    cur.execute(
        """
        SELECT
            r.repo_url,
            r.repo_name,
            r.repo_owner,
            r.team_id,
            r.default_branch,
            r.priority,
            r.status,
            r.jdk_version,
            m.source_file_count,
            m.total_loc,
            m.language,
            m.metadata
          FROM repositories AS r
     LEFT JOIN repos_metadata AS m
            ON r.repo_url = m.repo_url
         WHERE r.repo_url = ?
        """,
        (url,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Repository not found after admit.")

    try:
        stored_md = json.loads(row["metadata"] or "{}")
    except Exception:
        stored_md = {}

    return {
        "message":             "Repository admitted",
        "repo_url":            row["repo_url"],
        "repo_name":           row["repo_name"],
        "repo_owner":          row["repo_owner"],
        "team_id":             row["team_id"],
        "default_branch":      row["default_branch"],
        "priority":            row["priority"],
        "status":              row["status"],
        "jdk_version":         row["jdk_version"],
        "source_file_count":   row["source_file_count"],
        "total_loc":           row["total_loc"],
        "language":            row["language"],
        "metadata":            stored_md,
        "repo_path":           repo_path,
    }


@router.post("/admit_bulk")
async def admit_bulk(
    request: BulkRepoAdmitByUrlRequest,
    conn: sqlite3.Connection = Depends(get_db_write),
):
    """
    Bulk admit multiple URLs. Reports per-repo ok/error.
    """
    results = []
    for entry in request.repos:
        try:
            detail = await admit_repo(entry, conn)
            results.append({
                "repo_url": entry.repo_url,
                "status":   "ok",
                "detail":   detail,
            })
        except HTTPException as he:
            results.append({
                "repo_url": entry.repo_url,
                "status":   "error",
                "detail":   he.detail,
            })
    return results
