# modules/run_to_completion.py

"""
Orchestrate a full agent task from initial prompt through final tool call,
scoped to (agent_role, agent_id, repo_url).  Now passing explicit
repo_owner, repo_name for all tool executions.  The loop will
only exit once set_work_completed is successfully invoked (i.e. not rejected).
"""

import time
import sys

from fastapi import HTTPException
from shared.logger import logger
from shared.config import config

from modules.agent_context import set_current_agent
from modules.turns_list import (
    get_turns_list,
    add_turn_to_list,
    clear_turns_for_agent,
)
from modules.turns_single_run import run_single_turn
from modules.turns_processor import handle_context_violation
from modules.agents_temp_registry import get_agent_role as _fetch_agent_entry

# ----------------------------------------------------------------------------
# Now relying on the shared, hot-reloading ToolRegistryCache singleton
# ----------------------------------------------------------------------------
from modules.tool_registry_cache import get_tools_registry


def _run_to_completion_worker(
    agent_role:  str,
    agent_id:    str,
    repo_url:    str,
    repo_owner:  str = None,
    repo_name:   str = None,
    user_prompt: str = ""
) -> dict:
    start_time = time.time()

    # 1) set current-agent context
    set_current_agent(agent_role, agent_id, repo_url)

    # 2) load (or create) history
    history = get_turns_list(agent_role, agent_id, repo_url)

    # 2a) if the last turn was an accepted set_work_completed, reset history
    if history:
        last     = history[-1]
        tm       = last.turn_meta.get("tool_meta", {})
        tool_raw = last.messages.get("tool", {}).get("raw", {})
        if tool_raw.get("name") == "set_work_completed" and tm.get("rejection") is None:
            logger.info(
                "run_to_completion: detected prior successful set_work_completed; resetting history"
            )
            clear_turns_for_agent(agent_role, agent_id, repo_url)
            history = get_turns_list(agent_role, agent_id, repo_url)

    # 3) append the incoming user prompt as the next turn, if provided
    if user_prompt:
        from modules.unified_turn import UnifiedTurn

        turn_index = len(history)
        turn_meta = {
            "turn":             turn_index,
            "total_char_count": len(user_prompt),
            "finalized":        True,
            "tool_meta": {
                "status":         "",
                "execution_time": 0,
                "deleted":        False,
                "rejection":      None,
            }
        }
        raw_user = {"user": {"raw": {"role": "user", "content": user_prompt}}}
        user_turn = UnifiedTurn.create_turn(turn_meta, raw_user)
        add_turn_to_list(agent_role, agent_id, repo_url, user_turn)

    # 4) fetch full tool registry (cached)
    try:
        full_registry = get_tools_registry()
    except Exception as e:
        logger.error("run_to_completion: failed to fetch cached tool registry: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to fetch tools registry")

    # 5) fetch this agent-role’s registry entry (contains allowed_tools + optional model_name + reasoning_level)
    agent_entry = _fetch_agent_entry(agent_role)
    if agent_entry is None:
        # guard against missing role
        raise HTTPException(
            status_code=404,
            detail=f"Agent role '{agent_role}' not found"
        )

    # 5a) determine which LLM model to use
    model = agent_entry.model_name or config.get("LLM_MODEL", "gpt-4")
    logger.debug("Using LLM model_name = %s for agent_role = %s", model, agent_role)

    allowed = set(agent_entry.allowed_tools)

    logger.debug("==== run_to_completion DEBUG ====")
    logger.debug("Agent '%s' allowed_tools: %r", agent_role, allowed)

    # Dump the raw full registry for inspection
    if isinstance(full_registry, dict):
        logger.debug("FULL REGISTRY is a dict with %d entries", len(full_registry))
        for key, info in full_registry.items():
            logger.debug("  RAW REG[%r] → name=%r", key, info.get("name"))
    else:
        logger.debug("FULL REGISTRY is a list with %d entries", len(full_registry))
        for idx, info in enumerate(full_registry):
            logger.debug("  RAW REG[%d].get('name')= %r", idx, info.get("name"))

    def _tool_is_allowed(tool_key: str, info: dict, allowed_set: set) -> bool:
        fn_name        = info.get("name", "")
        short_from_key = tool_key[5:] if tool_key.startswith("tool_") else tool_key
        short_from_fn  = fn_name[5:]   if fn_name.startswith("tool_")   else fn_name
        candidates     = {tool_key, fn_name, short_from_key, short_from_fn}
        logger.debug(
            "  Checking tool_key=%r fn_name=%r → short_key=%r short_fn=%r ; intersects %r",
            tool_key, fn_name, short_from_key, short_from_fn,
            candidates & allowed_set
        )
        return bool(candidates & allowed_set)

    # 6) prune full registry down to exactly the tools this agent may use
    if isinstance(full_registry, dict):
        unified_registry = {
            k: v for k, v in full_registry.items()
            if _tool_is_allowed(k, v, allowed)
        }
    else:
        unified_registry = [
            info for info in full_registry
            if _tool_is_allowed(info.get("name", ""), info, allowed)
        ]

    if isinstance(unified_registry, dict):
        logger.debug(
            "AFTER-PRUNE REGISTRY dict has %d entries: %r",
            len(unified_registry), list(unified_registry.keys())
        )
    else:
        logger.debug(
            "AFTER-PRUNE REGISTRY list has %d entries: %r",
            len(unified_registry), [i.get("name") for i in unified_registry]
        )
    logger.debug("==== end DEBUG ====")

    # 7) determine max iterations (kept for instrumentation, not used to break)
    raw_max        = config.get("MAX_ITERATIONS", "0")
    max_iterations = int(raw_max) or None

    status    = "failure"
    response  = ""
    turn_next = 0

    # 8) main turn loop — never exits until set_work_completed succeeds
    while True:
        history = get_turns_list(agent_role, agent_id, repo_url)

        # 8a) context-size check / potential rejection
        if handle_context_violation(
            turns_list=history,
            current_turn=turn_next,
            agent_role=agent_role,
            agent_id=agent_id,
            repo_url=repo_url,
            unified_registry=unified_registry
        ):
            turn_next += 1
            continue

        # 8b) do one LLM+tool turn, passing model, repo_owner/repo_name and reasoning_effort through
        turn_next = run_single_turn(
            agent_role=agent_role,
            agent_id=agent_id,
            repo_url=repo_url,
            unified_registry=unified_registry,
            model=model,
            repo_owner=repo_owner,
            repo_name=repo_name,
            reasoning_effort=agent_entry.reasoning_level,
        )

        # 8c) only stop when we see an accepted set_work_completed call
        history   = get_turns_list(agent_role, agent_id, repo_url)
        last      = history[-1]
        tm        = last.turn_meta.get("tool_meta", {})
        tool_raw  = last.messages.get("tool", {}).get("raw", {})

        tool_name = tool_raw.get("name") or tm.get("name", "")
        rejected  = tm.get("rejection")

        if tool_name == "set_work_completed" and rejected is None:
            status   = "success"
            response = tool_raw.get("content", "")
            break

    total_time = time.time() - start_time
    result = {
        "agent_id":   agent_id,
        "agent_role": agent_role,
        "status":     status,
        "response":   response,
        "total_time": total_time,
    }
    logger.info("run_to_completion → %s", result)
    return result


def run_to_completion(
    agent_role:  str,
    agent_id:    str,
    repo_url:    str,
    repo_owner:  str = None,
    repo_name:   str = None,
    user_prompt: str = "",
) -> dict:
    """
    Public API: synchronously invoke the worker (no internal thread pool).
    """
    return _run_to_completion_worker(
        agent_role, agent_id, repo_url,
        repo_owner, repo_name, user_prompt
    )


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python run_to_completion.py <agent_role> <agent_id> <repo_url>")
        sys.exit(1)

    role     = sys.argv[1]
    agent_id = sys.argv[2]
    repo_url = sys.argv[3]

    # Optional flags for --owner and --name
    owner = None
    name  = None
    if "--owner" in sys.argv and "--name" in sys.argv:
        owner = sys.argv[sys.argv.index("--owner") + 1]
        name  = sys.argv[sys.argv.index("--name")  + 1]

    output = run_to_completion(
        agent_role=role,
        agent_id=agent_id,
        repo_url=repo_url,
        repo_owner=owner,
        repo_name=name,
        user_prompt="",
    )
    import json
    print(json.dumps(output, indent=2))
