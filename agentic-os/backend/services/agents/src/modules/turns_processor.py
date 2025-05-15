# modules/turns_processor.py

"""
This module processes turns for our conversation system. It performs tasks such as:

  • Recursively truncating verbose JSON fields.
  • Generating pretty-printed JSON debug dumps.
  • Calculating the total context size.
  • Finalizing turns (marking them complete and computing character counts).
  • Handling context violations.
  • Processing tool calls (executing approved tools and handling rejections).
  • Handling the assistant turn by appending messages to history—now supporting
    paired assistant+tool turns so that each tool-response lives alongside its
    originating assistant snippet.

Note: In the updated implementation (as of mid-2025), all tool-related messages now
use the role "tool" instead of the deprecated "function". Tool execution is now
called with explicit repo_owner and repo_name parameters instead of embedding them
in the input_args or relying on repo_url.
"""

from __future__ import annotations
import time
import json
import copy
from pprint import pformat
from typing import Any, Dict, List, Optional, Tuple

from shared.logger import logger
from shared.config import config
from modules.turns_list import add_turn_to_list, get_turns_list
from modules.unified_turn import UnifiedTurn

from modules.turns_executor import execute_and_wait
from modules.turns_purge import (                         # ← NEW: import purge routines
    purge_rejected_messages,
    purge_failed_messages,
    purge_one_time_messages,
    purge_build_messages,
    apply_pending_deletions,
)

# Constants used for truncating long content in debug dumps.
TRUNCATE_KEYS     = {"content", "output", "arguments", "normalized_args", "input_args"}
MAX_CONTENT_LEN   = 150
TRUNCATION_MARKER = "…"


def _recursively_truncate(data: Any, max_len: int, marker: str) -> Any:
    """
    Recursively truncate string values in a data structure (dict or list)
    for keys that are in TRUNCATE_KEYS.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            if k in TRUNCATE_KEYS:
                text = v if isinstance(v, str) else pformat(v, indent=4, sort_dicts=True)
                if len(text) > max_len:
                    half = (max_len - len(marker)) // 2
                    data[k] = text[:half] + marker + text[-half:]
                else:
                    data[k] = text
            else:
                _recursively_truncate(v, max_len, marker)
    elif isinstance(data, list):
        for item in data:
            _recursively_truncate(item, max_len, marker)
    return data


def pretty_format_json(
    d: dict,
    max_content_len: int = MAX_CONTENT_LEN,
    truncation_marker: str = TRUNCATION_MARKER
) -> str:
    """
    Return a pretty-printed string representation of a dict, truncating long values.
    Ensures that all JSON payloads remain readable.
    """
    dump = copy.deepcopy(d)
    _recursively_truncate(dump, max_content_len, truncation_marker)
    return pformat(dump, indent=4, sort_dicts=True)


def debug_dump_turn(turn: Any) -> str:
    """
    Return a debug-friendly string representation of a UnifiedTurn.
    """
    return pretty_format_json({
        "turn_meta": turn.turn_meta,
        "tool_meta": turn.tool_meta,
        "messages":  turn.messages,
    })


def _calculate_total_context_chars(turns_list: List[Any]) -> int:
    """
    Calculate the total number of characters for the conversation context
    in the given list of turns.
    """
    total = 0
    for turn in turns_list:
        turn_number = turn.turn_meta.get("turn", 0)
        if turn_number == 0:
            # For turn 0 (system/developer/user/tool), count each message's content length.
            for role in ("system", "developer", "user", "tool"):
                msg = turn.messages.get(role, {}).get("raw", {}).get("content", "")
                total += len(str(msg))
        else:
            total += turn.turn_meta.get("total_char_count", 0)
    logger.debug("Total context chars: %d over %d turns", total, len(turns_list))
    return total


def _finalize_turn(turn: Any) -> None:
    """
    Finalize a turn by marking it as 'finalized' and updating its total character count.
    """
    turn.turn_meta["finalized"] = True
    turn.tool_meta["deleted"] = False
    turn.tool_meta.pop("pending_deletion", None)
    assistant_content = turn.messages.get("assistant", {}).get("raw", {}).get("content", "")
    tool_content      = turn.messages.get("tool",      {}).get("raw", {}).get("content", "")
    turn.turn_meta["total_char_count"] = len(str(assistant_content)) + len(str(tool_content))


def _process_context_rejection(
    turns_list: List[Any],
    current_turn: int,
    unified_registry: dict
) -> Tuple[bool, Any]:
    """
    Evaluate if the current conversation context exceeds the allowed limit.
    If so, trigger a rejection turn via the turns_reject module.
    Returns (valid, rejection_turn).
    """
    limit = config["CONTEXT_CHAR_LIMIT_KB"] * 1024
    total = _calculate_total_context_chars(turns_list)
    logger.debug(
        "Context‐rejection check at turn %d: total=%d, limit=%d",
        current_turn, total, limit
    )
    if total >= limit:
        from modules.turns_reject import check_rejection
        rejection_turn = check_rejection(
            current_turn,
            turns=turns_list,
            unified_registry=unified_registry
        )
        logger.debug(
            "After rejection, turns_list:\n%s",
            pformat([debug_dump_turn(t) for t in turns_list])
        )
        return False, rejection_turn
    return True, None


def handle_context_violation(
    turns_list: List[Any],
    current_turn: int,
    agent_role: str,
    agent_id: str,
    repo_url: str,
    unified_registry: dict
) -> bool:
    """
    Check whether the accumulated context exceeds allowed limits.
    If the context is too long, either purge old history or inject a rejection turn.
    Returns True if a context violation was handled (and the LLM call should be skipped).
    """
    limit = config["CONTEXT_CHAR_LIMIT_KB"] * 1024
    total = _calculate_total_context_chars(turns_list)
    logger.debug(
        "handle_context_violation at turn %d: total=%d, limit=%d",
        current_turn, total, limit
    )

    if total <= limit:
        return False

    latest_turn = turns_list[-1]
    # If we've already asked for a purge once, now do the real purge:
    if latest_turn.tool_meta.get("rejection") == "context_exceeded":
        logger.info(
            "Persistent context violation at turn %d; purging history.",
            current_turn
        )
        logger.debug("Latest turn dump:\n%s", debug_dump_turn(latest_turn))
        turns_list.clear()
        turns_list.append(latest_turn)
        from modules.turns_list import save_turns_list
        save_turns_list(agent_role, agent_id, repo_url)
        return True

    # First time over-the-limit: inject a tool_purge_chat_turns call into this turn
    valid, _ = _process_context_rejection(turns_list, current_turn, unified_registry)
    if not valid:
        logger.info("Context limit exceeded at turn %d; asking assistant to purge.", current_turn)
        # Collect all prior turn IDs
        to_purge = [t.turn_meta["turn"] for t in turns_list[:-1]]
        # Mark this turn as a context_exceeded rejection
        latest_turn.tool_meta.update({
            "status":         "n/a",
            "execution_time": 0.0,
            "rejection":      "context_exceeded",
        })
        # Inject the purge instruction as a tool response
        latest_turn.messages.setdefault("tool", {"raw": {}})
        latest_turn.messages["tool"]["raw"].update({
            "role":         "tool",
            "name":         "tool_purge_chat_turns",
            "tool_call_id": None,
            "content":      json.dumps({"message_ids": to_purge}),
        })
        _finalize_turn(latest_turn)
        return True

    return False


def _process_tool_call(
    turn_number: int,
    unified_registry: dict,
    repo_owner: Optional[str],
    repo_name: Optional[str],
    repo_url: str
) -> Optional[Any]:
    """
    Process any tool call requested in the turn.
    Validates and executes the tool if permitted, or applies rejection logic if not.
    Returns the updated UnifiedTurn after processing.
    """
    from modules.turns_list import get_turns_list as _get_turns

    logger.debug("=== _process_tool_call start for turn %d ===", turn_number)
    global_turns = _get_turns()
    unified_turn = next(
        (t for t in reversed(global_turns)
         if t.turn_meta.get("turn") == turn_number),
        None
    )

    if unified_turn is None:
        logger.error("No turn found matching turn number %d", turn_number)
        return None

    # 1) Extract potential tool_call_id
    assistant_raw = unified_turn.messages.get("assistant", {}).get("raw", {})
    tool_calls    = assistant_raw.get("tool_calls") or []
    call_id       = (
        tool_calls[0].get("id")
        if tool_calls and isinstance(tool_calls, list)
        else None
    )
    logger.debug("Turn %d tool_call_id: %r", turn_number, call_id)

    # 2) Determine if a tool was requested
    tool_name = unified_turn.tool_meta.get("tool_name")
    logger.debug("Turn %d tool_name: %r", turn_number, tool_name)
    if not tool_name:
        unified_turn.turn_meta["finalized"] = True
        unified_turn.tool_meta.update({
            "status":           "n/a",
            "execution_time":   0.0,
            "rejection":        None,
            "deleted":          False,
            "pending_deletion": False,
        })
        _finalize_turn(unified_turn)
        logger.info("No tool call in turn %d; marked as n/a.", turn_number)
        # RUN PURGES for a non-tool turn as well
        purge_rejected_messages(global_turns, turn_number)
        purge_failed_messages(global_turns, turn_number)
        purge_one_time_messages(global_turns, turn_number)
        purge_build_messages(global_turns, turn_number)
        apply_pending_deletions(global_turns, turn_number)
        return unified_turn

    # 3) Raw vs normalized args
    raw_args = unified_turn.tool_meta.get("input_args", {})
    logger.debug("Turn %d raw input_args: %s", turn_number, pformat(raw_args))
    norm_args = unified_turn.tool_meta.get("normalized_args")
    exec_args = norm_args if isinstance(norm_args, dict) else raw_args

    # 4) Permission check
    allowed = tool_name in unified_registry
    logger.debug("Tool '%s' allowed in registry: %s", tool_name, allowed)
    if not allowed:
        from modules.turns_reject import check_rejection
        ut = check_rejection(
            turn_number,
            turns=global_turns,
            unified_registry=unified_registry
        )
        ut.tool_meta.update({
            "status":         "n/a",
            "execution_time": 0.0,
        })
        if ut.tool_meta.get("rejection"):
            ut.messages.setdefault("tool", {"raw": {}})
            ut.messages["tool"]["raw"].update({
                "role":         "tool",
                "name":         tool_name,
                "tool_call_id": call_id,
                "content":      json.dumps({"error": ut.tool_meta["rejection"]}),
            })
        logger.info("Tool '%s' not permitted; rejection applied.", tool_name)
        # RUN PURGES
        purge_rejected_messages(global_turns, turn_number)
        purge_failed_messages(global_turns, turn_number)
        purge_one_time_messages(global_turns, turn_number)
        purge_build_messages(global_turns, turn_number)
        apply_pending_deletions(global_turns, turn_number)
        return ut

    # 5) Pre-execution rejection
    from modules.turns_reject import check_rejection
    unified_turn = check_rejection(
        turn_number,
        turns=global_turns,
        unified_registry=unified_registry
    )
    if unified_turn.tool_meta.get("rejection"):
        unified_turn.tool_meta.update({
            "status":         "n/a",
            "execution_time": 0.0,
        })
        unified_turn.messages.setdefault("tool", {"raw": {}})
        unified_turn.messages["tool"]["raw"].update({
            "role":         "tool",
            "name":         tool_name,
            "tool_call_id": call_id,
            "content":      json.dumps({"error": unified_turn.tool_meta["rejection"]}),
        })
        logger.info(
            "Rejection pre-tool on turn %d; skipping execution.",
            turn_number
        )
        # RUN PURGES
        purge_rejected_messages(global_turns, turn_number)
        purge_failed_messages(global_turns, turn_number)
        purge_one_time_messages(global_turns, turn_number)
        purge_build_messages(global_turns, turn_number)
        apply_pending_deletions(global_turns, turn_number)
        return unified_turn

    # 6) Execute the tool via the background NATS-based executor.
    logger.debug(
        "Turn %d calling execute_and_wait with args:\n%s",
        turn_number,
        pformat({
            "tool_name":  tool_name,
            "input_args": exec_args,
            "metadata":   {},
            "turn_id":    str(turn_number),
            "repo_owner": repo_owner,
            "repo_name":  repo_name,
            "repo_url":   repo_url,
        })
    )

    try:
        result = execute_and_wait(
            tool_name=tool_name,
            input_args=exec_args,
            repo_owner=repo_owner,
            repo_name=repo_name,
            repo_url=repo_url,
            turn_id=str(turn_number),
        )
    except Exception as ex:
        elapsed = 0.0
        unified_turn.tool_meta.update({
            "status":         "failure",
            "execution_time": elapsed,
            "rejection":      None,
        })
        unified_turn.messages.setdefault("tool", {"raw": {}})
        unified_turn.messages["tool"]["raw"].update({
            "role":         "tool",
            "name":         tool_name,
            "tool_call_id": call_id,
            "content":      json.dumps({"error": str(ex)}),
        })
        logger.error(
            "execute_and_wait exception on turn %d: %s", turn_number, ex, exc_info=True
        )
        _finalize_turn(unified_turn)
        # RUN PURGES
        purge_rejected_messages(global_turns, turn_number)
        purge_failed_messages(global_turns, turn_number)
        purge_one_time_messages(global_turns, turn_number)
        purge_build_messages(global_turns, turn_number)
        apply_pending_deletions(global_turns, turn_number)
        return unified_turn

    logger.debug(
        "Turn %d execute_and_wait returned:\n%s", turn_number, pformat(result)
    )

    # 7) Attach the tool-response envelope
    elapsed   = result.get("execution_time", 0.0)
    resp_json = result.get("response", {})

    unified_turn.tool_meta.update({
        "status":         result.get("status", "failure"),
        "execution_time": elapsed,
        "rejection":      None,
    })

    unified_turn.messages.setdefault("tool", {"raw": {}})
    unified_turn.messages["tool"]["raw"].update({
        "role":         "tool",
        "name":         tool_name,
        "tool_call_id": call_id,
        "content":      json.dumps(resp_json),
    })

    if result.get("status") != "success":
        err = result.get("error") or result.get("output") or "Unknown tool error."
        unified_turn.messages["tool"]["raw"]["content"] = json.dumps({"error": err})
        logger.error("Tool '%s' failed on turn %d: %s", tool_name, turn_number, err)
        # RUN PURGES
        purge_rejected_messages(global_turns, turn_number)
        purge_failed_messages(global_turns, turn_number)
        purge_one_time_messages(global_turns, turn_number)
        purge_build_messages(global_turns, turn_number)
        apply_pending_deletions(global_turns, turn_number)
        return unified_turn

    # 8) Finalize successful turn
    _finalize_turn(unified_turn)
    logger.info("Tool '%s' succeeded on turn %d.", tool_name, turn_number)
    # RUN PURGES
    purge_rejected_messages(global_turns, turn_number)
    purge_failed_messages(global_turns, turn_number)
    purge_one_time_messages(global_turns, turn_number)
    purge_build_messages(global_turns, turn_number)
    apply_pending_deletions(global_turns, turn_number)
    return unified_turn


def handle_assistant_turn(
    assistant_response: Dict[str, Any],
    turn_counter: int,
    history: List[Any],
    execution_time: float,
    unified_registry: dict,
    agent_role: str,
    agent_id: str,
    repo_url: str,
    repo_owner: Optional[str],
    repo_name: Optional[str]
) -> None:
    """
    Process a parsed API-response dict (from parse_api_response):
      - If no tools were called, emit one assistant-only turn.
      - If tools were called, emit one paired assistant+tool turn per tool_call,
        pruning the assistant.tool_calls array to only the relevant entry.

    Repo_owner and repo_name are now passed in explicitly for tool execution.
    """
    assistant_env    = assistant_response.get("assistant", {})
    tools_env        = assistant_response.get("tools", [])
    tools_meta       = assistant_response.get("tools_meta", [])
    total_char_count = assistant_response.get("total_char_count", 0)

    # Case A: no tool calls → single assistant-only turn
    if not tools_env:
        turn_meta = {
            "turn":             turn_counter,
            "finalized":        False,
            "total_char_count": total_char_count,
            "tool_meta":        {},
        }
        raw_msgs = {
            "assistant": {"raw": assistant_env.get("raw", {})}
        }
        ut = UnifiedTurn.create_turn(turn_meta, raw_msgs)
        add_turn_to_list(agent_role, agent_id, repo_url, ut)
        logger.debug(
            "Appended assistant-only turn %d:\n%s",
            turn_counter, debug_dump_turn(ut)
        )
        # RUN PURGES
        global_turns = get_turns_list()
        purge_rejected_messages(global_turns, turn_counter)
        purge_failed_messages(global_turns, turn_counter)
        purge_one_time_messages(global_turns, turn_counter)
        purge_build_messages(global_turns, turn_counter)
        apply_pending_deletions(global_turns, turn_counter)
        return

    # Case B: one paired turn per tool_call
    for idx, (tool_env, tool_meta) in enumerate(zip(tools_env, tools_meta)):
        turn_num = turn_counter + idx

        # Compute char counts
        a_content = assistant_env["raw"].get("content", "") or ""
        t_content = tool_env["raw"].get("content", "") or ""
        total_ct  = len(a_content) + len(t_content)

        turn_meta = {
            "turn":             turn_num,
            "finalized":        False,
            "total_char_count": total_ct,
            "tool_meta":        tool_meta.copy(),
        }

        # Clone the assistant payload, prune tool_calls to this one
        orig   = assistant_env["raw"]
        pruned = orig.copy()
        calls  = orig.get("tool_calls", []) or []
        single = next(
            (c for c in calls if c.get("id") == tool_meta.get("tool_call_id")),
            None
        )
        pruned["tool_calls"] = [single] if single else []

        raw_msgs = {
            "assistant": {"raw": pruned},
            "tool":      {"raw": tool_env.get("raw", {})},
        }

        ut_pair = UnifiedTurn.create_turn(turn_meta, raw_msgs)
        add_turn_to_list(agent_role, agent_id, repo_url, ut_pair)
        logger.debug(
            "Appended paired turn %d:\n%s",
            turn_num, debug_dump_turn(ut_pair)
        )

        # Immediately process this tool call (exec or reject), then run purges
        _process_tool_call(turn_num, unified_registry, repo_owner, repo_name, repo_url)
        global_turns = get_turns_list()
        purge_rejected_messages(global_turns, turn_num)
        purge_failed_messages(global_turns, turn_num)
        purge_one_time_messages(global_turns, turn_num)
        purge_build_messages(global_turns, turn_num)
        apply_pending_deletions(global_turns, turn_num)
