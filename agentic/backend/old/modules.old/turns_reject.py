# modules/turns_reject.py

"""
This module centralizes rejection logic for turns.

It provides functions to detect potential rejections based on the current turn state and a set of defined policies.
It updates the "rejection" property in the turn's tool_meta if a condition is met.
Possible rejection types include:
  • reject-full: when context size exceeds the configured limit
  • reject-invalid: when mandatory tool data is missing or tool not found in registry
  • reject-denied: when tool access is denied
  • reject-dup: when a duplicate tool call is detected
  • reject-blind: when file-write has no prior evidence of file-read/write
  • reject-large: when file-read exceeds the file size limit
  • reject-useless: when a build or set-work-complete call is made without necessary prerequisites
  • reject-other: fallback (never triggers)
"""

import json
from pprint import pformat
from modules.logs import logger
from modules.turns_utils import get_normalized_file_key
from modules.config import config

def validate_build_status(tool_invocations_log, tool_name, config):
    """
    Checks that a successful build invocation has occurred prior to processing a subsequent tool call.
    
    Returns:
      (True, None) if successful,
      (False, error_message) otherwise.
    """
    build_logs = [entry for entry in tool_invocations_log
                  if entry.get("tool_name") in ("tool_build_gradle", "tool_build_test_gradle")]
    if not build_logs:
        return False, "No build tool invocation has been run. Please run a successful build first."
    latest_build = build_logs[-1]
    if not latest_build.get("build_success", False):
        return False, "The latest build execution failed. Please fix build errors before proceeding."
    return True, None

def validate_write_file(current_turn, history):
    """
    Verifies that a file-write operation in the current turn references a file that was previously
    successfully read or written in one of the earlier turns.
    
    The validation is performed using the normalized file identifier extracted from the current turn's input arguments.
    
    Returns:
      (True, normalized_key, None) if validation passes;
      (False, normalized_key, error_message) if it fails.
    """
    input_args = current_turn.tool_meta.get("input_args", {})
    args_str = json.dumps(input_args)
    normalized_key = get_normalized_file_key(args_str)
    if not normalized_key:
        return False, None, "Missing required file identifier in input arguments."
    
    for turn in history:
        if turn.turn_meta.get("turn", 0) >= current_turn.turn_meta.get("turn", 0):
            continue
        if turn.tool_meta.get("tool_name", "") not in ("tool_read_file", "tool_write_file"):
            continue
        if turn.tool_meta.get("status") != "success":
            continue
        if turn.tool_meta.get("deleted", False):
            continue
        if turn.tool_meta.get("rejection") is not None:
            continue
        evidence_args = turn.tool_meta.get("input_args", {})
        evidence_args_str = json.dumps(evidence_args)
        evidence_normalized = get_normalized_file_key(evidence_args_str)
        if evidence_normalized and evidence_normalized.lower() == normalized_key.lower():
            return True, normalized_key, None
    return False, normalized_key, f"No prior successful file-read/write evidence for '{normalized_key}' was found (reject-blind)."

def check_functions_by_signature_present(current_turn, history):
    """
    Checks that at least one prior turn in the history contains file evidence (from a file read/write operation)
    that matches the normalized file identifier in the current turn's tool call.
    
    Returns True if matching evidence is found; False otherwise.
    """
    input_args = current_turn.tool_meta.get("input_args", {})
    args_str = json.dumps(input_args)
    normalized_id = get_normalized_file_key(args_str)
    if not normalized_id:
        return False
    for turn in history:
        if turn.turn_meta.get("turn", 0) >= current_turn.turn_meta.get("turn", 0):
            continue
        if turn.tool_meta.get("tool_name", "") not in ("tool_read_file", "tool_write_file"):
            continue
        if turn.tool_meta.get("status") != "success":
            continue
        if turn.tool_meta.get("deleted", False):
            continue
        if turn.tool_meta.get("rejection") is not None:
            continue
        evidence_args = turn.tool_meta.get("input_args", {})
        evidence_args_str = json.dumps(evidence_args)
        evidence_normalized = get_normalized_file_key(evidence_args_str)
        if evidence_normalized and evidence_normalized.lower() == normalized_id.lower():
            return True
    return False

def validate_duplicate_tool_call(message_counter, tool_name, tool_type, tool_invocations_log, current_args_hash, unified_registry):
    """
    Checks previous tool invocations for a duplicate call based on the MD5 hash of normalized arguments.

    For mutating calls, an exact duplicate is flagged immediately.
    For readonly calls, if any intervening mutating call occurred between the candidate and current call,
    the duplicate check is reset.

    Returns the message_id of the first matching invocation if a duplicate is found; otherwise, returns None.
    """
    filtered_inv = sorted([inv for inv in tool_invocations_log
                             if inv.get("message_id", 0) < message_counter and
                                inv.get("tool_name") == tool_name and
                                not str(inv.get("status", "")).startswith("reject")],
                            key=lambda inv: inv.get("message_id", 0))
    candidate = next((inv for inv in filtered_inv if inv.get("args_hash", "") == current_args_hash), None)
    if candidate is None:
        return None

    if tool_type.lower() == "mutating":
        return candidate.get("message_id")

    candidate_id = candidate.get("message_id", 0)
    for inv in filtered_inv:
        inv_id = inv.get("message_id", 0)
        if candidate_id < inv_id < message_counter:
            other_tool = inv.get("tool_name")
            record = unified_registry.get(other_tool, {})
            other_type = record.get("type", "readonly").lower()
            if other_type == "mutating":
                return None
    return candidate.get("message_id")

def _calculate_total_context_chars(turns):
    total_chars = 0
    for t in turns:
        turn_num = t.turn_meta.get("turn", 0)
        if turn_num == 0:
            dev_msg = t.messages.get("developer", {}).get("raw", {}).get("content", "")
            user_msg = t.messages.get("user", {}).get("raw", {}).get("content", "")
            total_chars += len(str(dev_msg)) + len(str(user_msg))
        else:
            total_chars += t.turn_meta.get("total_char_count", 0)
    return total_chars

def _check_reject_full(turn, config):
    """
    Checks if the total context size exceeds the configured limit.
    """
    from modules.turns_list import get_turns_list
    turns = get_turns_list()
    total_chars = _calculate_total_context_chars(turns)
    limit_bytes = config.get("CONTEXT_CHAR_LIMIT_KB", 150) * 1024
    if total_chars >= limit_bytes:
        logger.debug("Rejection check 'reject-full' triggered: total_chars (%d) >= limit (%d)", total_chars, limit_bytes)
        return True
    return False

def _check_reject_invalid(turn, config):
    """
    Flags rejection if mandatory tool data is missing or if the tool is not found in the global registry.
    """
    tool_name = turn.tool_meta.get("tool_name")
    input_args = turn.tool_meta.get("input_args")
    if not tool_name or not isinstance(input_args, dict):
        logger.debug("Rejection check 'reject-invalid' triggered: missing tool_name or input_args")
        return True
    from modules.tools_registry import get_global_registry
    global_registry = get_global_registry()
    if tool_name not in global_registry:
        logger.debug("Rejection check 'reject-invalid' triggered: tool '%s' not found in registry", tool_name)
        return True
    return False

def _check_reject_denied(turn, config):
    """
    Flags rejection if access to the tool is denied.
    """
    if turn.tool_meta.get("access_denied", False):
        logger.debug("Rejection check 'reject-denied' triggered: access_denied flag is set")
        return True
    return False

def _check_reject_dup(turn, config):
    """
    Flags rejection if a duplicate tool call is detected.
    
    This check iterates over previous turns (ordered by turn number) using the new UnifiedTurn properties,
    specifically 'args_hash' and JSON-serialized normalized 'input_args'. The following rules apply:
    
    - For readonly calls:
      • Only non-deleted and non-rejected turns are considered.
      • A candidate duplicate is identified if either:
          - Both the current and candidate turns have matching 'args_hash' values, or
          - Their JSON-serialized normalized 'input_args' are identical.
      • Even if a candidate duplicate is found, if an intervening mutating call (with the same normalized filename)
        exists between the candidate and the current turn, the duplicate is allowed.
    
    - For mutating calls:
      • Deleted turns are also considered.
      • Any candidate duplicate (based on matching 'args_hash' or JSON-serialized 'input_args') immediately
        triggers a duplicate rejection.
    
    Note:
    - Deleted turns (turn.tool_meta["deleted"] True) are skipped for readonly calls, as they are treated as removed.
    - Turns already flagged with a non-None rejection are ignored in duplicate detection.
    
    Returns True if a duplicate is detected (and rejection should be triggered); otherwise, returns False.
    """
    from modules.turns_list import get_turns_list
    import json
    from modules.tools_registry import get_global_registry
    global_registry = get_global_registry()
    
    current_turns_list = get_turns_list()
    # Sort turns by turn number to ensure proper chronological order
    sorted_turns = sorted(current_turns_list, key=lambda t: t.turn_meta.get("turn", 0))
    
    current_turn_num = turn.turn_meta.get("turn", 0)
    # Locate current turn's index in the sorted list
    current_index = None
    for index, t in enumerate(sorted_turns):
        if t.turn_meta.get("turn", 0) == current_turn_num:
            current_index = index
            break
    if current_index is None:
        return False
    
    current_tool = turn.tool_meta.get("tool_name", "")
    current_hash = turn.tool_meta.get("args_hash", "")
    current_input_args = turn.tool_meta.get("input_args", {})
    current_normalized_filename = turn.tool_meta.get("normalized_filename", "").strip().lower()
    
    current_tool_info = global_registry.get(current_tool)
    current_type = "readonly"
    if current_tool_info:
        if hasattr(current_tool_info, "internal"):
            current_type = current_tool_info.internal.get("type", "readonly").lower()
        elif isinstance(current_tool_info, dict):
            current_type = current_tool_info.get("internal", {}).get("type", "readonly").lower()
    
    # Iterate over candidate turns (all turns before the current turn)
    for candidate in sorted_turns[:current_index]:
        # Skip candidate turns already flagged with a rejection
        if candidate.tool_meta.get("rejection") is not None:
            continue
        # For readonly calls, skip deleted turns as they are considered removed
        if current_type == "readonly" and candidate.tool_meta.get("deleted", False):
            continue
        if candidate.tool_meta.get("tool_name", "") != current_tool:
            continue
        
        candidate_hash = candidate.tool_meta.get("args_hash", "")
        duplicate = False
        # Compare using args_hash if available, otherwise use JSON-serialized normalized input_args.
        if current_hash and candidate_hash:
            if current_hash == candidate_hash:
                duplicate = True
        else:
            try:
                current_args_serialized = json.dumps(current_input_args, sort_keys=True)
                candidate_args_serialized = json.dumps(candidate.tool_meta.get("input_args", {}), sort_keys=True)
                if current_args_serialized == candidate_args_serialized:
                    duplicate = True
            except Exception as e:
                logger.error("Error comparing input_args for duplicate check: %s", e)
                continue
        
        if duplicate:
            if current_type == "readonly":
                # For readonly calls, check for an intervening mutating call between candidate and current turn with the same normalized filename.
                intervening_mutating = False
                for interm in sorted_turns:
                    interm_turn_num = interm.turn_meta.get("turn", 0)
                    if interm_turn_num <= candidate.turn_meta.get("turn", 0) or interm_turn_num >= current_turn_num:
                        continue
                    if interm.tool_meta.get("rejection") is not None:
                        continue
                    interm_tool = interm.tool_meta.get("tool_name", "")
                    interm_tool_info = global_registry.get(interm_tool)
                    interm_type = "readonly"
                    if interm_tool_info:
                        if hasattr(interm_tool_info, "internal"):
                            interm_type = interm_tool_info.internal.get("type", "readonly").lower()
                        elif isinstance(interm_tool_info, dict):
                            interm_type = interm_tool_info.get("internal", {}).get("type", "readonly").lower()
                    if interm_type == "mutating":
                        interm_normalized_filename = interm.tool_meta.get("normalized_filename", "").strip().lower()
                        if interm_normalized_filename == current_normalized_filename and not interm.tool_meta.get("deleted", False):
                            intervening_mutating = True
                            break
                if not intervening_mutating:
                    logger.debug("Rejection check 'reject-dup' triggered: duplicate found from turn %s", candidate.turn_meta.get("turn"))
                    return True
                else:
                    continue
            else:
                # For mutating calls, any duplicate candidate immediately triggers rejection, including deleted turns.
                logger.debug("Rejection check 'reject-dup' triggered (mutating call): duplicate found from turn %s", candidate.turn_meta.get("turn"))
                return True
    return False

def _check_reject_blind(turn, config):
    """
    Flags rejection if a file-write operation lacks prior successful file-read/write evidence.
    """
    if turn.tool_meta.get("tool_name") == "tool_write_file":
        from modules.turns_list import get_turns_list
        turns = get_turns_list()
        valid, normalized_key, err = validate_write_file(turn, turns)
        if not valid:
            logger.debug("Rejection check 'reject-blind' triggered: %s", err)
            return True
    return False

def _check_reject_large(turn, config):
    """
    Flags rejection if a file-read operation returns content larger than the file size limit.
    """
    if turn.tool_meta.get("tool_name") == "tool_read_file":
        content = turn.messages.get("tool", {}).get("raw", {}).get("content", "")
        if isinstance(content, str) and len(content) > config.get("FILE_SIZE_LIMIT_BYTES", 1000000):
            logger.debug("Rejection check 'reject-large' triggered: content length %d exceeds limit %d",
                         len(content), config.get("FILE_SIZE_LIMIT_BYTES", 1000000))
            return True
    return False

def _check_reject_useless(turn, config):
    """
    Flags rejection if a build or set-work-complete call is made without necessary prior successful mutating calls.
    """
    tool_name = turn.tool_meta.get("tool_name")
    from modules.turns_list import get_turns_list
    turns = get_turns_list()
    if tool_name == "tool_build":
        from modules.tools_registry import get_global_registry
        global_registry = get_global_registry()
        found_mutating = False
        for t in turns:
            if t.turn_meta.get("turn", 0) < turn.turn_meta.get("turn", 0):
                prev_tool = t.tool_meta.get("tool_name")
                if prev_tool in global_registry:
                    tool_info = global_registry[prev_tool]
                    prev_type = "readonly"
                    if hasattr(tool_info, "internal"):
                        prev_type = tool_info.internal.get("type", "readonly").lower()
                    elif isinstance(tool_info, dict):
                        prev_type = tool_info.get("internal", {}).get("type", "readonly").lower()
                    if prev_type == "mutating":
                        found_mutating = True
                        break
        if not found_mutating:
            logger.debug("Rejection check 'reject-useless' triggered: no prior mutating tool call found for tool_build")
            return True
    elif tool_name == "set-work-complete":
        valid_build_names = ("tool_build", "tool_build_gradle", "tool_build_test_gradle")
        found_build = False
        for t in turns:
            if t.turn_meta.get("turn", 0) < turn.turn_meta.get("turn", 0):
                if t.tool_meta.get("tool_name") in valid_build_names and t.tool_meta.get("status") == "success":
                    found_build = True
                    break
        if not found_build:
            logger.debug("Rejection check 'reject-useless' triggered: no prior successful build found for set-work-complete")
            return True
    return False

def _check_reject_other(turn, config):
    """
    Fallback check that never triggers a rejection.
    """
    return False

def check_rejection(turn_id):
    """
    Checks a UnifiedTurn (identified by turn_id) for potential rejections based on a series of policy checks.
    The first triggered check updates the turn's tool_meta["rejection"] property with a rejection type and stops further checks.
    If no check is triggered, the turn remains unmodified.
    """
    from modules.turns_list import get_turns_list
    turns = get_turns_list()
    target_turn = None
    for t in turns:
        if t.turn_meta.get("turn") == turn_id:
            target_turn = t
            break
    if target_turn is None:
        available_turns = sorted([t.turn_meta.get("turn") for t in turns])
        logger.debug("check_rejection: Turn %s not found. Available turns: %s", turn_id, available_turns)
        raise Exception(f"UnifiedTurn with turn number {turn_id} not found. Available turns: {available_turns}")
    rejection_checks = [
        (_check_reject_full, "reject-full"),
        (_check_reject_invalid, "reject-invalid"),
        (_check_reject_denied, "reject-denied"),
        (_check_reject_dup, "reject-dup"),
        (_check_reject_blind, "reject-blind"),
        (_check_reject_large, "reject-large"),
        (_check_reject_useless, "reject-useless"),
        (_check_reject_other, "reject-other")
    ]
    for check_func, rej_type in rejection_checks:
        try:
            if check_func(target_turn, config):
                target_turn.tool_meta["rejection"] = rej_type
                logger.info("Turn %s flagged with rejection: %s", turn_id, rej_type)
                return target_turn
        except Exception as e:
            logger.error("Error in rejection check %s: %s", rej_type, e)
    return target_turn

# ~~~~~~~~~~~~~~~~~ Test Harness ~~~~~~~~~~~~~~~~~
if __name__ == "__main__":
    logger.info("Running test harness for modules/turns_reject.py.")
    # Test stubs may be added here for rejection checks.
    pass