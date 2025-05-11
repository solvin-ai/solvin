# modules/run_to_completion.py

"""
Orchestrate a full agent task from initial prompt through final tool call,
scoped to (agent_role, agent_id, repo_url), now passing explicit repo_owner
and repo_name for all tool executions.  The loop will only exit once
set_work_completed is successfully invoked (i.e. not rejected).
"""

import time
import sys
import threading
import requests

from fastapi import HTTPException
from shared.logger import logger
from shared.config import config
from modules.agent_context import set_current_agent
from modules.turns_list import get_turns_list, add_turn_to_list
from modules.turns_single_run import run_single_turn
from modules.turns_processor import handle_context_violation

# Cache full tool registry (fetch once per process)
_FULL_TOOL_REGISTRY = None
_REGISTRY_LOCK = threading.Lock()


def _get_full_tool_registry() -> dict:
    """
    Fetch (and cache) the full tool registry—combining tools_list() + tools_info(meta+schema).
    """
    global _FULL_TOOL_REGISTRY
    if _FULL_TOOL_REGISTRY is None:
        with _REGISTRY_LOCK:
            if _FULL_TOOL_REGISTRY is None:
                from shared.client_tools import tools_list, tools_info

                try:
                    all_tools = tools_list()
                    tool_names = [t["tool_name"] for t in all_tools]
                except Exception as e:
                    logger.error("run_to_completion: tools_list() failed: %s", e, exc_info=True)
                    raise HTTPException(status_code=502, detail="Failed to fetch tools list")

                try:
                    _FULL_TOOL_REGISTRY = tools_info(
                        tool_names=tool_names,
                        meta=True,
                        schema=True
                    )
                except requests.HTTPError as e:
                    resp = e.response
                    body = resp.request.body or b"<empty>"
                    try:
                        body = body.decode("utf-8")
                    except Exception:
                        body = str(body)
                    logger.error(
                        "run_to_completion: tools_info() → HTTP %d\nURL: %s\nREQUEST BODY:\n%s\nRESPONSE BODY:\n%s",
                        resp.status_code, resp.url, body, resp.text,
                    )
                    raise HTTPException(status_code=502, detail="tools-info lookup failed")
                except Exception as e:
                    logger.error("run_to_completion: tools_info() crashed: %s", e, exc_info=True)
                    raise HTTPException(status_code=502, detail="Failed to fetch tool info")
    return _FULL_TOOL_REGISTRY


def run_to_completion(
    agent_role:  str,
    agent_id:    str,
    repo_url:    str,
    repo_owner:  str = None,
    repo_name:   str = None,
    user_prompt: str = ""
) -> dict:
    """
    Runs the agent from initial system+developer prompts through final tool call.

    Parameters:
      agent_role:  Role name (e.g. "root")
      agent_id:    Unique agent identifier
      repo_url:    Repository URL (used as unique key in turns DB)
      repo_owner:  GitHub owner/org of the repo (for tool execution)
      repo_name:   GitHub repo name (for tool execution)
      user_prompt: Optional user prompt (e.g. from tasks API)

    Returns:
      dict with keys: agent_id, agent_role, status, response, total_time
    """
    start_time = time.time()

    # 1) set current-agent context
    set_current_agent(agent_role, agent_id, repo_url)

    # 2) load and initialize history (turn-0 seeded if needed)
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
    full_registry = _get_full_tool_registry()

    # 5) fetch this agent-role’s registry entry (contains allowed_tools)
    from shared.client_agents import get_agent_role as _fetch_agent_entry
    agent_entry = _fetch_agent_entry(agent_role)
    allowed = set(agent_entry.get("allowed_tools", []))
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
        short_from_fn  = fn_name[5:]   if fn_name.startswith("tool_") else fn_name
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

        # 8b) do one LLM+tool turn, passing repo_owner/repo_name through
        turn_next = run_single_turn(
            agent_role=agent_role,
            agent_id=agent_id,
            repo_url=repo_url,
            unified_registry=unified_registry,
            repo_owner=repo_owner,
            repo_name=repo_name
        )

        # 8c) only stop when we see an accepted set_work_completed call
        history   = get_turns_list(agent_role, agent_id, repo_url)
        last      = history[-1]
        tm        = last.turn_meta.get("tool_meta", {})
        tool_raw  = last.messages.get("tool", {}).get("raw", {})

        # identify the tool name (might be in raw payload or in tool_meta)
        tool_name = tool_raw.get("name") or tm.get("name", "")
        rejected  = tm.get("rejection")

        if tool_name == "set_work_completed" and rejected is None:
            status   = "success"
            response = tool_raw.get("content", "")
            break

        # otherwise loop indefinitely until completion

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


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python run_to_completion.py <agent_role> <agent_id> <repo_url>")
        sys.exit(1)

    role      = sys.argv[1]
    agent_id  = sys.argv[2]
    repo_url  = sys.argv[3]

    # For manual testing you can supply --owner and --name flags, e.g.:
    # python run_to_completion.py root myagent https://... --owner myorg --name myrepo
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
    )
    import json
    print(json.dumps(output, indent=2))
