# modules/turns_duplicates.py

"""
Utility functions used specifically in duplication detection.
Adapted to the new “one tool turn per tool_call” model.
All argument‐hashing and normalization now lives in turn.tool_meta.
"""

import hashlib
from typing import Optional, List, Dict, Any

from shared.logger import logger
from modules.turns_utils import get_normalized_file_key
from modules.turns_list import get_turns_list

logger = logger


def compute_md5_hash(args_str: str) -> str:
    """
    Compute a compact Base64‐encoded MD5 hash of the argument string.
    Returns empty string if args_str is blank or "{}".
    """
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


def get_last_accepted_message(current_turn: int, tool_name: str):
    """
    Return the last non‐rejected, non‐deleted turn for this tool before current_turn.
    """
    turns_list = get_turns_list()
    for turn in reversed(turns_list):
        tnum = turn.turn_meta.get("turn")
        if tnum is None or tnum >= current_turn:
            continue
        if turn.tool_meta.get("rejection") is not None:
            continue
        if turn.tool_meta.get("deleted", False):
            continue
        if turn.tool_meta.get("pending_deletion", False):
            continue
        tool_msg = turn.messages.get("tool")
        if not tool_msg:
            continue
        if tool_msg["raw"].get("role", "").lower() != "tool":
            continue
        if turn.tool_meta.get("tool_name") == tool_name:
            return turn
    return None


def has_intervening_mutators(
    start_turn: int,
    current_turn: int,
    normalized_key: str,
    unified_registry: Dict[str, Any]
) -> bool:
    """
    Return True if any mutating tool turn lies strictly between start_turn and current_turn.
    Special case: any run_bash counts as a mutator even without a normalized_filename.
    """
    turns_list = get_turns_list()
    for turn in turns_list:
        tnum = turn.turn_meta.get("turn")
        if tnum is None or tnum <= start_turn or tnum >= current_turn:
            continue
        if turn.tool_meta.get("rejection") is not None:
            continue
        if turn.tool_meta.get("deleted", False) or turn.tool_meta.get("pending_deletion", False):
            continue
        tool_msg = turn.messages.get("tool")
        if not tool_msg or tool_msg["raw"].get("role", "").lower() != "tool":
            continue

        name = turn.tool_meta.get("tool_name")
        if not name:
            continue
        tool_obj = unified_registry.get(name)
        if not tool_obj:
            raise ValueError(f"Tool '{name}' not in registry when scanning for mutators")

        # any run_bash in between always counts as a mutator
        if name == "run_bash":
            logger.debug("Intervening mutator (run_bash) in turn %d; blocking dedupe", tnum)
            return True

        # for other mutating tools, only block if they actually mutated this same file
        if str(tool_obj.get("type", "")).lower() == "mutating":
            mut_key = (turn.tool_meta.get("normalized_filename") or "").lower().strip()
            if mut_key == normalized_key:
                logger.debug(
                    "Intervening mutator on same file in turn %d (tool=%s, file=%s)",
                    tnum, name, mut_key
                )
                return True

    return False


def check_duplicate(
    current_turn: int,
    tool_name: str,
    tool_args_str: str,
    tool_invocations_log: List[Dict[str, Any]],
    unified_registry: Dict[str, Any]
) -> Optional[int]:
    """
    Checks for duplicate tool invocations before the current turn.
    Returns the turn number of a duplicate if found; otherwise, None.
    """
    turns_list = get_turns_list()
    tool_obj = unified_registry.get(tool_name)
    if not tool_obj:
        logger.error("check_duplicate: Tool '%s' not found in registry.", tool_name)
        raise ValueError("Unknown tool: " + tool_name)

    policy = str(tool_obj.get("preservation_policy", "")).lower()
    ttype   = str(tool_obj.get("type", "")).lower()

    # current‐args hash
    current_hash = compute_md5_hash(tool_args_str)
    # fallback normalized key
    normalized_key = ""
    try:
        normalized_key = get_normalized_file_key(tool_args_str).lower().strip()
    except Exception as e:
        logger.debug("Normalization failed: %s", e)

    logger.debug(
        "check_duplicate: tool=%s, turn=%d, policy=%s, type=%s, hash=%s, norm=%s",
        tool_name, current_turn, policy, ttype, current_hash, normalized_key
    )

    # Policy "until-build": use external invocation log + last accepted turn
    if policy == "until-build":
        last_turn = get_last_accepted_message(current_turn, tool_name)
        if last_turn and not has_intervening_mutators(
            last_turn.turn_meta["turn"], current_turn, normalized_key, unified_registry
        ):
            for inv in tool_invocations_log:
                if inv.get("tool_name") != tool_name:
                    continue
                if str(inv.get("status", "")).startswith("reject"):
                    continue
                if inv.get("args_hash", "") == current_hash:
                    dup = inv.get("turn")
                    logger.debug("Duplicate (until-build) found at turn %s", dup)
                    return dup
        return None

    # Other policies: scan history turns
    candidate = None
    for turn in reversed(turns_list):
        tnum = turn.turn_meta.get("turn")
        if tnum is None or tnum >= current_turn:
            continue
        if turn.tool_meta.get("rejection") is not None \
           or turn.tool_meta.get("deleted", False) \
           or turn.tool_meta.get("pending_deletion", False):
            continue
        if turn.tool_meta.get("tool_name") != tool_name:
            continue

        # match by args_hash if present
        if current_hash and turn.tool_meta.get("args_hash") == current_hash:
            candidate = turn
            break

        # else match by normalized_filename
        if not current_hash and normalized_key:
            if turn.tool_meta.get("normalized_filename", "").lower().strip() == normalized_key:
                candidate = turn
                break

    if not candidate:
        return None

    # Non-mutating tools: ensure no mutator between candidate and now
    if ttype != "mutating":
        cand_turn = candidate.turn_meta["turn"]
        if has_intervening_mutators(cand_turn, current_turn, normalized_key, unified_registry):
            logger.debug("Mutator intervened after candidate turn %s; not a duplicate", cand_turn)
            return None

    dup_turn = candidate.turn_meta["turn"]
    logger.debug("Duplicate found at turn %s", dup_turn)
    return dup_turn
