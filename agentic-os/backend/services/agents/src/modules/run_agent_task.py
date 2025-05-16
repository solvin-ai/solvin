# modules/run_agent_task.py

from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any

from modules.run_to_completion import run_to_completion as tools_run_to_completion
from shared.logger import logger
from shared.config import config
from modules.agents_running import seed_agent, set_current_agent

# ----------------------------------------------------------------
# Thread‐pool for all run_agent_task calls
# ----------------------------------------------------------------
_MAX_AGENT_TASK_THREADS = int(config.get("MAX_AGENT_TASK_THREADS", "5"))
_AGENT_TASK_EXECUTOR = ThreadPoolExecutor(
    max_workers=_MAX_AGENT_TASK_THREADS,
    thread_name_prefix="run-agent-task-worker"
)

def _worker(
    agent_role:   str,
    repo_url:     str,
    user_prompt:  Optional[str],
    agent_id:     Optional[str],
    repo_owner:   Optional[str],
    repo_name:    Optional[str],
) -> Dict[str, Any]:
    """
    1) Seed (or re‐use) an agent:
       - If agent_role == "root", always use ID "001".
       - Otherwise, derive/use agent_id or user_prompt.
    2) Mark that agent current.
    3) If no user_prompt was provided, return immediately.
    4) Otherwise, drive the run_to_completion loop.
    """
    # 1) seed or reuse; special‐case "root"
    if agent_role == "root":
        local_agent_id = seed_agent(
            agent_role=agent_role,
            repo_url=repo_url,
            agent_id="001",
            user_prompt=None,
        )
    else:
        local_agent_id = seed_agent(
            agent_role=agent_role,
            repo_url=repo_url,
            agent_id=agent_id,
            user_prompt=user_prompt,
        )

    # 2) ensure request‐context is set
    set_current_agent(agent_role, local_agent_id, repo_url)

    # 3) if caller only wanted to seed (no prompt), return now
    if user_prompt is None:
        return {
            "success": True,
            "agent_id": local_agent_id,
            "task_result": None
        }

    # 4) Drive the agent through to completion via the Tools service
    try:
        run_resp = tools_run_to_completion(
            agent_role=agent_role,
            agent_id=local_agent_id,
            repo_url=repo_url,
            repo_owner=repo_owner,
            repo_name=repo_name,
            user_prompt=user_prompt,
        )
    except Exception as e:
        logger.error("run_to_completion exception", exc_info=True)
        return {
            "success": False,
            "agent_id": local_agent_id,
            "task_result": str(e),
        }

    # 5) return success or errors
    if isinstance(run_resp, dict) and run_resp.get("errors"):
        return {
            "success": False,
            "agent_id": local_agent_id,
            "task_result": run_resp["errors"]
        }

    return {
        "success": True,
        "agent_id": local_agent_id,
        "task_result": run_resp.get("data")
    }

def run_agent_task(
    agent_role:   str,
    repo_url:     str,
    user_prompt:  Optional[str] = None,
    agent_id:     Optional[str] = None,
    repo_owner:   Optional[str] = None,
    repo_name:    Optional[str] = None,
) -> Dict[str, Any]:
    """
    Public entrypoint: schedule the agent workflow in a background thread.
    Returns: { success, agent_id, task_result }.
    """
    try:
        future = _AGENT_TASK_EXECUTOR.submit(
            _worker,
            agent_role,
            repo_url,
            user_prompt,
            agent_id,
            repo_owner,
            repo_name,
        )
        return future.result()
    except Exception as e:
        logger.error("run_agent_task uncaught exception", exc_info=True)
        return {
            "success": False,
            "agent_id": None,
            "task_result": str(e),
        }
