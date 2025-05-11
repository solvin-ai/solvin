# routers/router_delete.py

from fastapi import APIRouter, HTTPException, Depends
import os
import shutil
import sqlite3

from modules.routers_core import get_db_write, REPOS_DIR
from modules.routers_schema import RepoDeleteRequest

router = APIRouter(prefix="/repos", tags=["Repos"])


@router.delete("/delete")
def delete_repo(
    request: RepoDeleteRequest,
    conn: sqlite3.Connection = Depends(get_db_write),
):
    """
    Delete a repository by URL:
      • Remove its working directory under REPOS_DIR/<repo_name>
      • Optionally remove its database record (cascades to repos_metadata)
    """
    # 1) Look up repo_name in the DB
    cur = conn.cursor()
    cur.execute(
        "SELECT repo_name FROM repositories WHERE repo_url = ?",
        (request.repo_url,),
    )
    row = cur.fetchone()
    repo_name = row["repo_name"] if row else None

    # 2) Fallback: derive name from URL
    if not repo_name:
        url = request.repo_url.strip().rstrip("/")
        parts = url.split("/")
        raw = parts[-1]
        repo_name = raw[:-4] if raw.endswith(".git") else raw

    # 3) Filesystem removal
    fs_deleted = False
    folder = os.path.join(REPOS_DIR, repo_name)
    if os.path.isdir(folder):
        try:
            shutil.rmtree(folder)
            fs_deleted = True
        except Exception as e:
            raise HTTPException(500, f"Filesystem removal failed: {e}")

    msg = f"Filesystem removal: {'succeeded' if fs_deleted else 'not found or nothing to delete'}."

    # 4) Database removal (if requested)
    if request.remove_db:
        cur.execute(
            "DELETE FROM repositories WHERE repo_url = ?",
            (request.repo_url,),
        )
        deleted = cur.rowcount > 0
        conn.commit()
        msg += f" Database record {'removed' if deleted else 'not found'}."

    return {"message": msg}
