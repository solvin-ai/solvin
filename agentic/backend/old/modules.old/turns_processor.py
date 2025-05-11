# modules/turns_processor.py

from __future__ import annotations
import json
import datetime
import copy
from pprint import pformat
from typing import Any, Dict, List, Optional, Tuple

from modules.logs import logger

# ------------------------------------------------------------------------------
# Constants & Generic Formatting Helper
# ------------------------------------------------------------------------------

MAX_CONTENT_LEN = 150
TRUNCATION_MARKER = "..."
# The set of keys that will be truncated if their string length exceeds MAX_CONTENT_LEN.
TRUNCATE_KEYS = {"content", "output", "arguments", "normalized_args", "input_args"}

def recursively_truncate(data, max_content_len: int, truncation_marker: str):
    """
    Recursively traverse data (which may be a dict or list) and, for any dictionary key
    in TRUNCATE_KEYS (e.g. "content", "output", "arguments", "normalized_args", "input_args"),
    first convert its value to a string (if it isn’t already) and then, if the string’s length exceeds
    max_content_len, truncate it by keeping the beginning and end with the truncation_marker in between.

    This preserves the previous behavior even for keys whose values are arrays or other non-string structures.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key in TRUNCATE_KEYS:
                # Ensure the value is a string by pretty-printing non-string objects.
                if not isinstance(value, str):
                    value_str = pformat(value, indent=4, sort_dicts=True)
                else:
                    value_str = value
                if len(value_str) > max_content_len:
                    half_len = (max_content_len - len(truncation_marker)) // 2
                    truncated_value = value_str[:half_len] + truncation_marker + value_str[-half_len:]
                    data[key] = truncated_value
                else:
                    # Even if not over the limit, converting to a string ensures consistent output.
                    data[key] = value_str
            else:
                recursively_truncate(value, max_content_len, truncation_marker)
    elif isinstance(data, list):
        for item in data:
            recursively_truncate(item, max_content_len, truncation_marker)
    return data

def pretty_format_json(data: dict,
                       max_content_len: int = MAX_CONTENT_LEN,
                       truncation_marker: str = TRUNCATION_MARKER) -> str:
    """
    Returns a deep-copied, pretty-printed JSON/dict string.

    This version recursively searches for any keys named in TRUNCATE_KEYS
    and, if the associated string value (or its pretty-printed representation) exceeds max_content_len,
    truncates it.
    """
    formatted = copy.deepcopy(data)
    recursively_truncate(formatted, max_content_len, truncation_marker)
    return pformat(formatted, indent=4, sort_dicts=True)

def debug_dump_turn(turn: Any) -> str:
    """
    Returns a full dump string of a UnifiedTurn object's key attributes,
    using our pretty JSON formatter.
    """
    dump = {
        "turn_meta": turn.turn_meta,
        "tool_meta": turn.tool_meta,
        "messages": turn.messages,
    }
    return pretty_format_json(dump)

# ------------------------------------------------------------------------------
# Internal Helper Functions
# ------------------------------------------------------------------------------

def _get_message_content_length(message: Dict[str, Any]) -> int:
    """
    Returns the length of the content in the message's "raw" field.
    Assumes that the required structure exists.
    """
    raw = message["raw"]
    content = raw["content"]
    return len(str(content))

def _update_total_char_count(unified_turn: Any) -> Any:
    """
    Updates the total_char_count for the UnifiedTurn by summing the character
    counts from the assistant and tool messages.
    """
    turn_id = unified_turn.turn_meta["turn"]
    assistant_content = str(unified_turn.messages["assistant"]["raw"]["content"])
    tool_content = str(unified_turn.messages["tool"]["raw"]["content"])
    total_chars = len(assistant_content) + len(tool_content)
    unified_turn.turn_meta["total_char_count"] = total_chars
    logger.debug("New total_char_count for turn %s: %s", turn_id, total_chars)
    return unified_turn

def _calculate_total_context_chars(turns_list: List[Any]) -> int:
    """
    Returns the total character count from all UnifiedTurn objects in turns_list.
    For turn 0 (the “initial” turn), if a total_char_count is not set, it computes
    the count using the developer and user messages.
    """
    total_chars = 0
    for turn in turns_list:
        turn_num = turn.turn_meta["turn"]
        if turn_num == 0:
            dev_content = turn.messages["developer"]["raw"]["content"]
            user_content = turn.messages["user"]["raw"]["content"]
            count = len(dev_content) + len(user_content)
        
        logger.debug("Turn %s: stored total_char_count: %d", turn_num, count)
        count = turn.turn_meta["total_char_count"]
        total_chars += count
    logger.debug("Total context characters computed: %d for %d total turns", total_chars, len(turns_list))
    return total_chars

def _finalize_turn(unified_turn: Any) -> None:
    """
    Resets deletion flags and ensures the turn is marked as finalized,
    then updates its total character count.
    """
    unified_turn.turn_meta["finalized"] = True
    unified_turn.tool_meta["deleted"] = False
    if "pending_deletion" in unified_turn.tool_meta:
        unified_turn.tool_meta["pending_deletion"] = False
    _update_total_char_count(unified_turn)

# ------------------------------------------------------------------------------
# Core Processing Functions
# ------------------------------------------------------------------------------

def _process_context_rejection(turns_list: List[Any], config: Dict[str, Any],
                               current_turn: int) -> Tuple[bool, Optional[Any]]:
    """
    Checks if the accumulated context size in turns_list exceeds the threshold specified
    in config. If so, invokes the rejection detection via check_rejection and returns (False, rejection_turn).
    Otherwise, returns (True, None).

    The context limit is expected to be in KB and will be converted to bytes.
    """
    total_chars = _calculate_total_context_chars(turns_list)
    converted_limit = config["CONTEXT_CHAR_LIMIT_KB"] * 1024  # KB -> bytes
    logger.debug("Context check at turn %d: total_chars=%d, limit (in bytes)=%d",
                 current_turn, total_chars, converted_limit)
    if total_chars >= converted_limit:
        from modules.turns_reject import check_rejection
        rejection_turn = check_rejection(current_turn)
        logger.debug("After rejection check, turns_list dump:\n%s",
                     pformat([debug_dump_turn(t) for t in turns_list]))
        return False, rejection_turn
    return True, None

def _process_tool_call(turn_number: int) -> Optional[Any]:
    """
    Validates and executes the tool call for the UnifiedTurn identified by turn_number.
    It searches for the turn in the global turns list and either finalizes the turn as
    'skipped', calls the tool execution routine, or triggers a rejection detection.
    Updates the tool message meta with the char_count of the tool response and updates
    the tool meta "status" even if the tool call did not succeed.
    If there is either a tool status failure or a rejection, the tool message raw "content"
    is updated with the corresponding failure or rejection reason.
    """
    from modules.turns_list import get_turns_list
    global_turns = get_turns_list()

    # Directly find the UnifiedTurn with the matching turn number.
    unified_turn = next(turn for turn in reversed(global_turns)
                        if turn.turn_meta["turn"] == turn_number)

    from modules.tools_registry import get_global_registry
    unified_registry = get_global_registry()

    tool_call_id = unified_turn.messages["tool"]["raw"]["tool_call_id"]

    # If no tool was designated, mark the turn as "skipped".
    if not unified_turn.tool_meta["tool_name"]:
        logger.info("No tool call found; marking turn %s as finalized with status 'skipped'.", turn_number)
        unified_turn.turn_meta["finalized"] = True
        unified_turn.tool_meta["status"] = "skipped"
        unified_turn.tool_meta["execution_time"] = 0.0
        unified_turn.tool_meta["rejection"] = None
        if "pending_deletion" in unified_turn.tool_meta:
            unified_turn.tool_meta["pending_deletion"] = False
        _update_total_char_count(unified_turn)
        logger.info("Final UnifiedTurn state for turn %s:\n%s", turn_number, debug_dump_turn(unified_turn))
        return unified_turn

    tool_name = unified_turn.tool_meta["tool_name"]
    input_args = unified_turn.tool_meta["input_args"]
    logger.info("Found tool call: '%s' with input_args: %s for turn %s", tool_name, input_args, turn_number)

    # Fetch the tool object from the registry (direct indexing).
    tool_obj = unified_registry[tool_name]
    if not tool_obj:
        logger.info("Tool '%s' not found in registry (not permitted) for turn %s.", tool_name, turn_number)
        from modules.turns_reject import check_rejection
        unified_turn = check_rejection(turn_number)
        if unified_turn.tool_meta.get("rejection"):
            unified_turn.messages["tool"]["raw"]["content"] = "Rejection: " + unified_turn.tool_meta.get("rejection")
        logger.info("Final UnifiedTurn state for turn %s:\n%s", turn_number, debug_dump_turn(unified_turn))
        return unified_turn

    # Perform pre-execution rejection check before executing the tool.
    from modules.turns_reject import check_rejection
    unified_turn = check_rejection(turn_number)
    if unified_turn.tool_meta.get("rejection") is not None:
        unified_turn.messages["tool"]["raw"]["content"] = "Rejection: " + unified_turn.tool_meta.get("rejection")
        logger.info("Rejection triggered for turn %s before tool execution; skipping tool call.", turn_number)
        logger.info("Final UnifiedTurn state for turn %s:\n%s", turn_number, debug_dump_turn(unified_turn))
        return unified_turn

    # Execute the tool using the tools executor.
    from modules.tools_executor import execute_tool
    logger.info("Executing tool '%s' for turn %s.", tool_name, turn_number)
    result = execute_tool(
        tool_name, input_args, registry=unified_registry
    )
    elapsed = result["execution_time"]

    # Convert the tool response into a string so we can measure its length.
    tool_response_str = json.dumps(result["response"])

    # Update the tool message meta with the char_count.
    if "meta" in unified_turn.messages["tool"]:
        unified_turn.messages["tool"]["meta"]["char_count"] = len(tool_response_str)
    else:
        unified_turn.messages["tool"]["meta"] = {"char_count": len(tool_response_str)}

    logger.debug("Tool output for turn %s:\n%s", turn_number,
                 pretty_format_json(result["response"], max_content_len=MAX_CONTENT_LEN, truncation_marker=TRUNCATION_MARKER))

    # Update the tool meta "status" even in the error case.
    if result["status"] != "success":
        unified_turn.tool_meta["status"] = result["status"]
        error_value = result.get("error", "").strip()
        output_value = result.get("output", "").strip()
        if error_value:
            err_msg = error_value
        elif output_value:
            err_msg = output_value
        else:
            err_msg = "Tool execution failed without error message."
        unified_turn.messages["tool"]["raw"]["content"] = "Failure: " + err_msg
        logger.error("Tool execution error for turn %s.", turn_number)
        return unified_turn

    logger.info("Tool JSON response indicates success for turn %s.", turn_number)
    unified_turn.tool_meta["status"] = "success"
    unified_turn.tool_meta["execution_time"] = elapsed
    unified_turn.tool_meta["rejection"] = None

    # Save the tool response string (we already computed its char_count above).
    unified_turn.messages["tool"]["raw"]["content"] = tool_response_str
    _finalize_turn(unified_turn)

    # Invoke rejection checks to ensure duplicate (or other) rejections are applied even if the tool call succeeded.
    from modules.turns_reject import check_rejection
    unified_turn = check_rejection(turn_number)
    logger.debug("Turn %s after tool call processing:\n%s", turn_number, debug_dump_turn(unified_turn))
    logger.info("Final UnifiedTurn state for turn %s:\n%s", turn_number, debug_dump_turn(unified_turn))
    return unified_turn

def handle_context_violation(turns_list: List[Any], config: Dict[str, Any],
                             current_turn: int, agent_role: str, agent_id: str,
                             interactive_pause_fn: Any, save_fn: Any) -> bool:
    """
    Checks if the accumulated context size exceeds the configured limit.

    If so:
      • For persistent context rejections where the latest turn already indicates a violation,
        older turns are purged leaving the last rejection turn.
      • Otherwise, it updates the current turn with rejection feedback.

    In both cases, the turns list is persisted via save_fn and an interactive pause is triggered.

    Returns True if a context violation was detected/handled; otherwise False.
    """
    total_chars = _calculate_total_context_chars(turns_list)
    converted_limit = config["CONTEXT_CHAR_LIMIT_KB"] * 1024  # KB -> bytes
    logger.debug("handle_context_violation invoked at turn %s: total_chars=%s, limit (in bytes)=%s",
                 current_turn, total_chars, converted_limit)

    if total_chars <= converted_limit:
        logger.debug("Context within threshold at turn %s.", current_turn)
        return False

    latest_turn = turns_list[-1]
    if latest_turn and latest_turn.tool_meta["rejection"] == "context_exceeded":
        logger.info("Persistent context violation detected at turn %s. Purging older turns.", current_turn)
        logger.debug("Latest rejection turn dump:\n%s", debug_dump_turn(latest_turn))
        turns_list.clear()
        turns_list.append(latest_turn)
        save_fn(agent_role, agent_id)
        interactive_pause_fn(config, current_turn)
        logger.debug("After purging, turns_list dump:\n%s",
                     pformat([debug_dump_turn(t) for t in turns_list]))
        return True

    valid_context, rejection_turn = _process_context_rejection(turns_list, config, current_turn)
    if not valid_context:
        logger.info("Context size exceeded at turn %s. Rejection feedback applied.", current_turn)
        logger.debug("Updated rejection turn dump:\n%s", debug_dump_turn(rejection_turn))
        save_fn(agent_role, agent_id)
        interactive_pause_fn(config, current_turn)
        return True

    return False

def handle_assistant_turn(assistant_response: Dict[str, Any],
                          turn_counter: int,
                          history: List[Any],
                          execution_time: float) -> Any:
    """
    Processes an assistant turn by creating a new UnifiedTurn, appending it to
    the conversation history, and delegating tool call processing if the response includes a tool call.

    Parameters:
      assistant_response : Dict containing the assistant's response. Expected to include
                           keys "assistant", "tool", and optionally "tool_meta" and "total_char_count"
                           from the enrichment done in parse_api_response.
      turn_counter       : The current turn number.
      history            : The conversation history (list of UnifiedTurn objects).
      execution_time     : Time (in seconds) taken by the LLM to generate the response.

    Returns:
      The newly created UnifiedTurn.
    """
    raw_assistant = assistant_response["assistant"]
    assistant_content = raw_assistant["raw"].get("content") or ""
    input_char_count = len(assistant_content)

    turn_meta = {
        "turn": turn_counter,
        "finalized": False,
        "total_char_count": assistant_response.get("total_char_count", input_char_count)
    }
    # Use the enriched tool_meta if available from the API response;
    # otherwise, fall back to default values.
    enriched_tool_meta = assistant_response.get("tool_meta")
    if not enriched_tool_meta:
        enriched_tool_meta = {
            "tool_name": assistant_response["tool"]["raw"].get("name", ""),
            "execution_time": execution_time,
            "pending_deletion": False,
            "deleted": False,
            "rejection": None,
            "status": "n/a",
            "args_hash": "",
            "preservation_policy": "",
            "input_args": {},
            "normalized_args": {},
            "normalized_filename": ""
        }
    else:
        # Ensure the execution_time is updated.
        enriched_tool_meta["execution_time"] = execution_time

    meta = { **turn_meta, "tool_meta": enriched_tool_meta }
    from modules.unified_turn import UnifiedTurn
    assistant_turn = UnifiedTurn.create_turn(meta, assistant_response)
    history.append(assistant_turn)
    logger.debug("Created assistant turn %s:\n%s", turn_counter, debug_dump_turn(assistant_turn))
    
    tool_call_id = assistant_response["tool"]["raw"].get("tool_call_id", "")
    if turn_counter > 0 and tool_call_id:
        logger.info("Processing tool call for turn %s.", turn_counter)
        _process_tool_call(turn_counter)
    else:
        logger.debug("Assistant turn %s did not include any tool calls.", turn_counter)
    
    return assistant_turn

# ------------------------------------------------------------------------------
# Demo / Module Self-Test
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    from modules.unified_turn import UnifiedTurn
    
    # Create a dummy UnifiedTurn for demonstration.
    dummy_turn_meta = {"turn": 1, "finalized": False, "total_char_count": 0}
    dummy_tool_meta = {
        "tool_name": "dummy_tool",
        "input_args": {"param1": "value1"},
        "preservation_policy": "always",
        "normalized_args": {},
        "args_hash": "dummyhash",
        "normalized_filename": "",
        "status": "",
        "execution_time": 0.0,
        "deleted": False,
        "rejection": None
    }
    dummy_assistant_message = {
        "meta": {"timestamp": datetime.datetime.now().isoformat(),
                 "original_message_id": 0, "char_count": 21},
        "raw": {
            "role": "assistant",
            "content": "Assistant message",
            "tool_calls": [{
                "id": "call_Dummy",
                "function": {"name": "dummy_tool", "arguments": "{\"param1\": \"value1\"}"},
                "type": "function"
            }]
        }
    }
    dummy_tool_message = {
        "meta": {"timestamp": datetime.datetime.now().isoformat(),
                 "original_message_id": 1, "char_count": 0},
        "raw": {"role": "tool", "content": "",
                "tool_call_id": "call_Dummy", "name": "dummy_tool"}
    }
    dummy_messages = {"assistant": dummy_assistant_message, "tool": dummy_tool_message}
    dummy_turn = UnifiedTurn(dummy_turn_meta, dummy_tool_meta, dummy_messages)
    
    from modules.turns_list import initialize_turns_list
    global_turns = initialize_turns_list("test", "001")
    global_turns.append(dummy_turn)
    
    # Example: Process context rejection with a limit of 150 KB.
    config = {"CONTEXT_CHAR_LIMIT_KB": 150}  # Example limit in KB.
    valid_context, rejection_turn = _process_context_rejection(global_turns, config, current_turn=2)
    if not valid_context:
        logger.info("Context exceeded. Rejection feedback applied:\n%s", debug_dump_turn(rejection_turn))
    
    processed_turn = _process_tool_call(1)
    logger.info("Processed UnifiedTurn for turn 1:\n%s", debug_dump_turn(processed_turn))
