# modules/turns_duplicates.py

"""
Utility functions used specifically in duplication detection.
"""

import hashlib
from typing import Optional
from modules.logs import logger
from modules.turns_utils import get_normalized_file_key
from modules.turns_list import get_turns_list

def compute_md5_hash(args_str: str) -> str:
    stripped = args_str.strip()
    if stripped in ("", "{}"):
        return ""
    try:
        digest = hashlib.md5(args_str.encode("utf-8")).digest()
        # Base64 encode and remove trailing '=' for compactness.
        return __import__("base64").b64encode(digest).decode("utf-8").rstrip("=")
    except Exception as exc:
        logger.error("Error computing MD5 hash for tool arguments: %s", exc)
        return ""

# -------- Duplication Detection Functions --------

def get_last_accepted_message(current_turn: int, tool_name: str):
    """
    Searches through the global turns list for the last accepted message for a given tool,
    prior to the specified current_turn.

    Parameters:
      current_turn (int): The current turn number.
      tool_name (str): The name of the tool.

    Returns:
      The last accepted turn (if found) or None.
    """
    turns_list = get_turns_list()
    logger.debug("get_last_accepted_message: Looking for last accepted message for tool '%s' before turn %s",
                 tool_name, current_turn)
    for turn in reversed(turns_list):
        turn_number = turn.turn_meta.get("turn")
        logger.debug("Checking turn %s with tool '%s'", turn_number, turn.tool_meta.get("tool_name", "N/A"))
        if turn_number >= current_turn:
            continue
        if (turn.tool_meta.get("rejection") is not None or 
            turn.tool_meta.get("deleted", False) or 
            turn.tool_meta.get("pending_deletion", False)):
            continue
        tool_msg = turn.messages.get("tool") if "tool" in turn.messages else None
        if not tool_msg:
            continue
        role = tool_msg["raw"].get("role", "").lower()
        if role != "tool":
            continue
        stored_tool = turn.tool_meta.get("tool_name")
        if stored_tool == tool_name:
            return turn
    return None

def has_intervening_mutators(start_turn: int, current_turn: int, unified_registry) -> bool:
    """
    Scans for any intervening mutator turns between start_turn and current_turn.

    Parameters:
      start_turn (int): The turn number from which to start checking.
      current_turn (int): The current turn number.
      unified_registry (dict): The unified tools registry.

    Returns:
      True if an intervening mutator is found; False otherwise.
    """
    turns_list = get_turns_list()
    logger.debug("has_intervening_mutators: Checking intervening turns between %s and %s",
                 start_turn, current_turn)
    for turn in turns_list:
        turn_number = turn.turn_meta.get("turn")
        if turn_number <= start_turn or turn_number >= current_turn:
            continue
        if turn.tool_meta.get("rejection") is not None:
            continue
        tool_msg = turn.messages.get("tool") if "tool" in turn.messages else None
        if not tool_msg:
            continue
        role = tool_msg["raw"].get("role", "").lower()
        if role != "tool":
            continue
        tool_name_in_turn = turn.tool_meta.get("tool_name")
        if tool_name_in_turn:
            # Lookup using dict get.
            tool_obj = unified_registry.get(tool_name_in_turn)
            if not tool_obj:
                import pprint
                pp = pprint.PrettyPrinter(indent=4)
                raise ValueError("Tool '" + str(tool_name_in_turn) +
                                 "' not found in registry while checking intervening mutators. Message details: " +
                                 pp.pformat(turn.__dict__))
            try:
                turn_type = tool_obj["type"].lower()
            except Exception as e:
                logger.error("has_intervening_mutators: Error accessing type for tool '%s': %s", tool_name_in_turn, e)
                import pprint
                pp = pprint.PrettyPrinter(indent=4)
                raise ValueError("Tool '" + str(tool_name_in_turn) +
                                 "' missing required configuration (type). Details: " +
                                 pp.pformat(turn.__dict__))
            if turn_type == "mutating":
                logger.debug("has_intervening_mutators: Found intervening mutator in turn %s (tool: %s)",
                             turn_number, tool_name_in_turn)
                return True
    return False

def check_duplicate(current_turn: int,
                    tool_name: str,
                    tool_args_str: str,
                    tool_invocations_log: list,
                    unified_registry) -> Optional[int]:
    """
    Checks for duplicate tool invocations before the current turn.

    Parameters:
      current_turn (int): The current turn number.
      tool_name (str): The name of the tool.
      tool_args_str (str): The string representation of the tool arguments.
      tool_invocations_log (list): Log of previous tool invocations.
      unified_registry (dict): The unified tools registry.

    Returns:
      Optional[int]: The turn number of a duplicate invocation if found; otherwise, None.
    """
    turns_list = get_turns_list()
    tool_obj = unified_registry.get(tool_name)
    if not tool_obj:
        logger.error("check_duplicate: Tool '%s' not found in unified registry.", tool_name)
        raise ValueError("Tool not found in registry: " + tool_name)
    policy = tool_obj["preservation_policy"].lower()
    current_type = tool_obj["type"].lower()
    try:
        normalized_key = get_normalized_file_key(tool_args_str)
        normalized_key = normalized_key.lower().strip()
        logger.debug("check_duplicate: Normalized key for tool '%s': '%s'", tool_name, normalized_key)
    except Exception as e:
        logger.error("check_duplicate: Error normalizing arguments: %s", e)
        normalized_key = ""
    logger.debug("check_duplicate: Tool='%s', type='%s', policy='%s', current_turn=%s",
                 tool_name, current_type, policy, current_turn)
    if policy == "until-build":
        current_args_hash = compute_md5_hash(tool_args_str)
        logger.debug("check_duplicate: Computed args hash: %s", current_args_hash)
        last_turn = get_last_accepted_message(current_turn, tool_name)
        if last_turn is not None:
            if has_intervening_mutators(last_turn.turn_meta.get("turn"), current_turn, unified_registry):
                logger.debug("check_duplicate: Intervening mutator found; duplicate not confirmed.")
                return None
            for inv in tool_invocations_log:
                entry_turn = inv.get("turn")
                if entry_turn is None:
                    continue
                if inv.get("tool_name") == tool_name:
                    if str(inv.get("status", "")).startswith("reject"):
                        continue
                    if inv.get("args_hash", "") == current_args_hash:
                        logger.debug("check_duplicate: Duplicate found: turn %s", entry_turn)
                        return entry_turn
        return None
    else:
        candidate = None
        for turn in reversed(turns_list):
            turn_number = turn.turn_meta.get("turn")
            if turn_number >= current_turn:
                continue
            if (turn.tool_meta.get("rejection") is not None or 
                turn.tool_meta.get("deleted", False) or 
                turn.tool_meta.get("pending_deletion", False)):
                continue
            tool_msg = turn.messages.get("tool") if "tool" in turn.messages else None
            if not tool_msg:
                continue
            role = tool_msg["raw"].get("role", "").lower()
            if role != "tool":
                continue
            stored_tool = turn.tool_meta.get("tool_name")
            if stored_tool != tool_name:
                continue
            tool_calls = tool_msg["raw"].get("tool_calls", [])
            if not tool_calls:
                continue
            prev_args_str = tool_calls[0].get("function", {}).get("arguments", "")
            try:
                prev_normalized = get_normalized_file_key(prev_args_str)
                prev_normalized = prev_normalized.lower().strip()
            except Exception:
                prev_normalized = ""
            if prev_normalized != normalized_key:
                continue
            candidate = turn
            logger.debug("check_duplicate: Candidate duplicate found: turn %s", turn_number)
            break
        if candidate is None:
            return None
        if current_type != "mutating":
            candidate_turn = candidate.turn_meta.get("turn")
            for turn in turns_list:
                turn_number = turn.turn_meta.get("turn")
                if candidate_turn < turn_number < current_turn:
                    if turn.tool_meta.get("rejection") is not None:
                        continue
                    tool_in_turn = turn.tool_meta.get("tool_name")
                    if not tool_in_turn:
                        continue
                    tool_for_turn = unified_registry.get(tool_in_turn)
                    if not tool_for_turn:
                        import pprint
                        pp = pprint.PrettyPrinter(indent=4)
                        raise ValueError("Tool '" + str(tool_in_turn) +
                                         "' not found in registry while scanning candidate duplicate. Turn details: " +
                                         pp.pformat(turn.__dict__))
                    try:
                        turn_type = tool_for_turn["type"].lower()
                    except Exception as e:
                        logger.error("check_duplicate: Error accessing type for tool '%s': %s", tool_in_turn, e)
                        import pprint
                        pp = pprint.PrettyPrinter(indent=4)
                        raise ValueError("Tool '" + str(tool_in_turn) +
                                         "' missing required configuration (type). Turn details: " +
                                         pp.pformat(turn.__dict__))
                    if turn_type == "mutating":
                        logger.debug("check_duplicate: Intervening mutator detected in turn %s (tool '%s').",
                                     turn_number, tool_in_turn)
                        return None
        return candidate.turn_meta.get("turn")
