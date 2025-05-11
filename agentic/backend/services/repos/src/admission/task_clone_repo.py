# admission/task_clone_repo.py

from admission import admission_task
from modules.git import clone_repo
from shared.logger import logger

@admission_task("clone_repo")
def clone_repo_task(repo_path, repo_info):
    """
    Admission task for cloning a repo. 
    If repo_info['repo_url'] is present, clone to the desired folder. 
    Updates repo_info['local_path'].
    """
    repo_url = repo_info.get("repo_url")
    branch   = repo_info.get("branch")
    dest_name= repo_info.get("repo_name")
    
    if not repo_url:
        logger.info("[admission] No repo_url provided; skipping clone.")
        repo_info["local_path"] = repo_path
        return

    # Always use central clone_repo utility for handling all git logic
    local_path = clone_repo(repo_url, branch=branch, dest_name=dest_name)
    logger.info(f"[admission] Repo cloned (or ready): {repo_url} → {local_path}")
    repo_info["local_path"] = local_path
