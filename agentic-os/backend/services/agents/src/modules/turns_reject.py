# modules/turns_reject.py

"""
Turn-based rejection logic for message-centric agent stack.

All tool registry access goes through shared.client_tools.
No legacy tools_registry, no fallbacks, no defensive glue.

Each check now expects (turn: UnifiedTurn, config: dict, turns: list, unified_registry: dict).
If a particular check does not need one or more of those parameters it should ignore them.
"""

import json
from pprint import pformat
from shared.logger import logger
from modules.turns_utils import get_normalized_file_key
from shared.config import config
from shared.client_tools import tools_info

# Stateless utility, no global registry allowed

def validate_build_status(tool_invocations_log, tool_name, config):
    build_logs = [entry for entry in tool_invocations_log
                  if entry.get("tool_name") in ("tool_build_gradle", "tool_build_test_gradle")]
    if not build_logs:
        return False, "No build tool invocation has been run. Please run a successful build first."
    latest_build = build_logs[-1]
    if not latest_build.get("build_success", False):
        return False, "The latest build execution failed. Please fix build errors before proceeding."
    return True, None

def validate_write_file(current_turn, history):
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

def _check_reject_full(turn, config, turns, unified_registry):
    total_chars = _calculate_total_context_chars(turns)
    limit_bytes = config.get("CONTEXT_CHAR_LIMIT_KB", 150) * 1024
    if total_chars >= limit_bytes:
        logger.debug("Rejection check 'reject-full' triggered: total_chars (%d) >= limit (%d)", total_chars, limit_bytes)
        return True
    return False

def _check_reject_invalid(turn, config, turns, unified_registry):
    tool_name = turn.tool_meta.get("tool_name")
    input_args = turn.tool_meta.get("input_args")
    if not tool_name or not isinstance(input_args, dict):
        logger.debug("Rejection check 'reject-invalid' triggered: missing tool_name or input_args")
        return True
    if tool_name not in unified_registry:
        logger.debug("Rejection check 'reject-invalid' triggered: tool '%s' not found in registry", tool_name)
        return True
    return False

def _check_reject_denied(turn, config, turns, unified_registry):
    if turn.tool_meta.get("access_denied", False):
        logger.debug("Rejection check 'reject-denied' triggered: access_denied flag is set")
        return True
    return False

def _check_reject_dup(turn, config, turns, unified_registry):
    current_turn_num = turn.turn_meta.get("turn", 0)
    sorted_turns = sorted(turns, key=lambda t: t.turn_meta.get("turn", 0))
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
    record = unified_registry.get(current_tool) or {}
    current_type = record.get("type", "readonly").lower()
    for candidate in sorted_turns[:current_index]:
        if candidate.tool_meta.get("rejection") is not None:
            continue
        if current_type == "readonly" and candidate.tool_meta.get("deleted", False):
            continue
        if candidate.tool_meta.get("tool_name", "") != current_tool:
            continue
        candidate_hash = candidate.tool_meta.get("args_hash", "")
        duplicate = False
        if current_hash and candidate_hash and current_hash == candidate_hash:
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
                intervening_mutating = False
                for interm in sorted_turns:
                    interm_turn_num = interm.turn_meta.get("turn", 0)
                    if interm_turn_num <= candidate.turn_meta.get("turn", 0) or interm_turn_num >= current_turn_num:
                        continue
                    if interm.tool_meta.get("rejection") is not None:
                        continue
                    interm_tool = interm.tool_meta.get("tool_name", "")
                    interm_type = (unified_registry.get(interm_tool) or {}).get("type", "readonly").lower()
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
                logger.debug("Rejection check 'reject-dup' triggered (mutating call): duplicate found from turn %s", candidate.turn_meta.get("turn"))
                return True
    return False

def _check_reject_blind(turn, config, turns, unified_registry):
    if turn.tool_meta.get("tool_name") == "tool_write_file":
        valid, normalized_key, err = validate_write_file(turn, turns)
        if not valid:
            logger.debug("Rejection check 'reject-blind' triggered: %s", err)
            return True
    return False

def _check_reject_large(turn, config, turns, unified_registry):
    if turn.tool_meta.get("tool_name") == "tool_read_file":
        content = turn.messages.get("tool", {}).get("raw", {}).get("content", "")
        if isinstance(content, str) and len(content) > config.get("FILE_SIZE_LIMIT_BYTES", 1000000):
            logger.debug("Rejection check 'reject-large' triggered: content length %d exceeds limit %d",
                         len(content), config.get("FILE_SIZE_LIMIT_BYTES", 1000000))
            return True
    return False

def _check_reject_useless(turn, config, turns, unified_registry):
    tool_name = turn.tool_meta.get("tool_name")
    if tool_name == "tool_build":
        found_mutating = False
        for t in turns:
            if t.turn_meta.get("turn", 0) < turn.turn_meta.get("turn", 0):
                prev_tool = t.tool_meta.get("tool_name")
                prev_type = (unified_registry.get(prev_tool) or {}).get("type", "readonly").lower()
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

def _check_reject_other(turn, config, turns, unified_registry):
    return False

def check_rejection(turn_id, turns, unified_registry):
    """
    Checks a UnifiedTurn (by turn_id in provided `turns` list) for possible rejections.
    `unified_registry` is required and must come from shared.client_tools, not legacy.
    """
    target_turn = None
    for t in turns:
        if t.turn_meta.get("turn") == turn_id:
            target_turn = t
            break
    if target_turn is None:
        available_turns = sorted([t.turn_meta.get("turn") for t in turns])
        logger.debug("check_rejection: Turn %s not found. Available turns: %s", turn_id, available_turns)
        raise Exception(f"UnifiedTurn with turn number {turn_id} not found. Available turns: {available_turns}")
    # All checks now operate in message-centric, explicit-registry mode:
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
            # pass all required data explicitly, no globals allowed
            if check_func(target_turn, config, turns, unified_registry):
                target_turn.tool_meta["rejection"] = rej_type
                logger.info("Turn %s flagged with rejection: %s", turn_id, rej_type)
                return target_turn
        except Exception as e:
            logger.error("Error in rejection check %s: %s", rej_type, e)
    return target_turn

if __name__ == "__main__":
    logger.info("Test: modules/turns_reject.py now fully message/registry-centric. No tools_registry is loaded or referenced.")
    # Add test calls here as needed to check rejection pathway
