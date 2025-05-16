# modules/run_agent_task.py

from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any

from modules.run_to_completion import run_to_completion as tools_run_to_completion
from shared.logger import logger
from shared.config import config
from modules.agents_running import (
    seed_agent,
    set_current_agent_tuple,
    get_current_agent_tuple,
)
from modules.agent_call_graph import record_spawn

# ----------------------------------------------------------------------------
# Thread‐pool for all run_agent_task calls
# ----------------------------------------------------------------------------
_MAX_AGENT_TASK_THREADS = int(config.get("MAX_AGENT_TASK_THREADS", "5"))
_AGENT_TASK_EXECUTOR   = ThreadPoolExecutor(
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
    1) Snapshot the parent agent
    2) If parent.role == agent_role, reuse that agent_id
       else seed_agent(...) → creates or reuses exactly one agent per role/repo
       and record the spawn edge
    3) Mark the chosen agent as current in this thread
    4) Drive run_to_completion
    5) Restore the parent agent before returning
    """
    # 1) snapshot parent
    parent = get_current_agent_tuple()  # type: ignore
    parent_key = (parent[0], parent[1]) if parent else ("<none>", "<none>")

    # 2) spawn or reuse
    if parent and parent[0] == agent_role:
        # already running this role, reuse it
        local_agent_id = parent[1]
        logger.debug(f"_worker: reusing existing {agent_role}:{local_agent_id}")
    else:
        # must pass user_prompt here (caller responsibility)
        local_agent_id = seed_agent(
            agent_role=agent_role,
            repo_url=repo_url,
            agent_id=agent_id,
            user_prompt=user_prompt,
        )
        record_spawn(parent_key, (agent_role, local_agent_id))
        logger.debug(f"_worker: recorded spawn {parent_key} → {(agent_role, local_agent_id)}")

    # 3) mark current in this thread
    set_current_agent_tuple(agent_role, local_agent_id, repo_url)

    # 4) run to completion
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
        result = {
            "success":     False,
            "agent_id":    local_agent_id,
            "task_result": str(e),
        }
    else:
        if isinstance(run_resp, dict) and run_resp.get("errors"):
            result = {
                "success":     False,
                "agent_id":    local_agent_id,
                "task_result": run_resp["errors"],
            }
        else:
            result = {
                "success":     True,
                "agent_id":    local_agent_id,
                "task_result": run_resp.get("data"),
            }
    finally:
        # 5) restore parent pointer
        if parent:
            set_current_agent_tuple(*parent)
        else:
            set_current_agent_tuple(None, None, None)

    return result

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
            "success":     False,
            "agent_id":    None,
            "task_result": str(e),
        }
