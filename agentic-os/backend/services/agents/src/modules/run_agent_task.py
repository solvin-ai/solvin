# modules/run_agent_task.py

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, Tuple

from shared.logger import logger
from shared.config import config

from modules.agents_running import (
    seed_agent,
    get_current_agent_tuple,
    set_thread_current_agent_tuple,
    pop_current_agent
)
from modules.run_to_completion import run_to_completion as tools_run_to_completion
from modules.agent_call_graph import record_spawn
from modules.turns_list import update_turns_metadata

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
    user_prompt:  str,
    agent_id:     str,
    repo_owner:   Optional[str],
    repo_name:    Optional[str],
    parent_ctx:   Optional[Tuple[str, str, str]],
) -> Dict[str, Any]:
    """
    Worker thread for a single run_agent_task invocation.
    1) Re‐install parent context (threads do NOT inherit it).
    2) Seed the agent in this thread’s DB connection (idempotent + sets thread‐local).
    3) Record spawn in the call‐graph.
    4) Mark agent state = running.
    5) Call run_to_completion.
    Finally, mark idle and restore or clear parent context.
    """
    # 1) re‐install parent context
    if parent_ctx:
        set_thread_current_agent_tuple(*parent_ctx)

    # 2) re‐seed our agent in this thread (ensures the FK row is visible,
    #    and also installs (role,id,repo) in thread‐local)
    seed_agent(agent_role=agent_role, repo_url=repo_url, agent_id=agent_id)

    # 3) record the spawn for the call‐graph (skip self‐loops)
    pkey = (parent_ctx[0], parent_ctx[1]) if parent_ctx else ("<none>", "<none>")
    if pkey != (agent_role, agent_id):
        record_spawn(pkey, (agent_role, agent_id))
    logger.debug(f"_worker: spawn {pkey} → {(agent_role, agent_id)}")

    # 4) mark as running
    update_turns_metadata(agent_role, agent_id, repo_url, "state", "running")

    try:
        # 5) drive the agent to completion
        run_resp = tools_run_to_completion(
            agent_role=agent_role,
            agent_id=agent_id,
            repo_url=repo_url,
            repo_owner=repo_owner,
            repo_name=repo_name,
            user_prompt=user_prompt,
        )

        if isinstance(run_resp, dict) and run_resp.get("errors"):
            return {
                "success":     False,
                "agent_id":    agent_id,
                "task_result": run_resp["errors"],
            }
        else:
            return {
                "success":     True,
                "agent_id":    agent_id,
                "task_result": run_resp.get("data"),
            }

    except Exception as e:
        logger.error("run_to_completion exception", exc_info=True)
        return {
            "success":     False,
            "agent_id":    agent_id,
            "task_result": str(e),
        }

    finally:
        # 6) mark idle
        update_turns_metadata(agent_role, agent_id, repo_url, "state", "idle")
        # 7) restore or clear parent context
        if parent_ctx:
            set_thread_current_agent_tuple(*parent_ctx)
        else:
            set_thread_current_agent_tuple(None, None, None)


def run_agent_task(
    agent_role:  str,
    repo_url:    str,
    user_prompt: str,
    agent_id:    Optional[str] = None,
    repo_owner:  Optional[str] = None,
    repo_name:   Optional[str] = None,
) -> Dict[str, Any]:
    """
    Public entrypoint: schedule the agent workflow in a background thread.

    • user_prompt: required, non‐empty.
    • If agent_id is omitted or blank, compute as MD5(user_prompt).
    • Capture the current thread‐local context (parent) before seeding.
    • Seed the agent here (DB insert + thread‐local).
    • Dispatch a worker thread that re‐seeds and runs to completion.
    """
    # 1) enforce non‐empty prompt
    if not user_prompt or not user_prompt.strip():
        raise ValueError("run_agent_task: user_prompt is required and must be non-empty")
    prompt = user_prompt.strip()

    # 2) derive agent_id if missing
    if not agent_id or not agent_id.strip():
        agent_id = hashlib.md5(prompt.encode("utf-8")).hexdigest()

    # 3) capture caller’s context
    parent_ctx = get_current_agent_tuple()

    # 4) seed the agent now (DB insert + thread‐local set)
    local_agent_id = seed_agent(agent_role=agent_role, repo_url=repo_url, agent_id=agent_id)

    # 5) dispatch worker
    try:
        future = _AGENT_TASK_EXECUTOR.submit(
            _worker,
            agent_role,
            repo_url,
            prompt,
            local_agent_id,
            repo_owner,
            repo_name,
            parent_ctx,
        )
        return future.result()
    except Exception as e:
        logger.error("run_agent_task uncaught exception", exc_info=True)
        return {
            "success":     False,
            "agent_id":    None,
            "task_result": str(e),
        }
    finally:
        # restore the caller’s context by popping this seed
        pop_current_agent()
