# modules/turns_purge.py

"""
Description: This module manages deletion (purging) of turns from the conversation history,
based on various preservation policies. It now assumes that all conversation turns are
UnifiedTurn objects whose data is directly available via turn.turn_meta and turn.tool_meta.
For turn-0 entries, the role is determined from the unified messages stored in turn._messages.
All extra defensive checks have been removed.
"""

import os
import logging
from pprint import pformat

from modules.logs import logger
from modules.unified_turn import UnifiedTurn, PreservationPolicy
from modules.turns_utils import get_normalized_file_key, normalize_policy

logger.setLevel(logging.DEBUG)

def get_turn_role(turn: UnifiedTurn) -> str:
    """
    Returns the normalized role for a UnifiedTurn.
    For turn 0, it checks the turn._messages for a "developer" (or "user") role.
    For all other turns, the role is assumed to be "tool".
    """
    if turn.turn_meta["turn"] == 0:
        if "developer" in turn._messages:
            return turn._messages["developer"]["raw"]["role"].lower().strip()
        elif "user" in turn._messages:
            return turn._messages["user"]["raw"]["role"].lower().strip()
        return ""
    else:
        return "tool"

def is_turn0_message(turn: UnifiedTurn) -> bool:
    """
    Returns True if the turn is a turn-0 message.
    """
    return turn.turn_meta["turn"] == 0

def extract_tool_name(turn: UnifiedTurn) -> str:
    """
    For a tool UnifiedTurn, returns the tool name stored in tool_meta.
    """
    return turn.tool_meta["tool_name"]

DEFAULT_PENDING_DELETION_OFFSET = 2

def schedule_pending_deletion(turn: UnifiedTurn, current_turn: int, deletion_reason: str, 
                              offset: int = DEFAULT_PENDING_DELETION_OFFSET):
    """
    Schedules a turn for deletion by setting pending deletion flags in tool_meta.
    """
    deletion_turn = current_turn + offset
    turn.tool_meta["pending_deletion"] = True
    turn.tool_meta["pending_deletion_turn"] = deletion_turn
    turn.tool_meta["pending_deletion_reason"] = deletion_reason
    logger.debug("schedule_pending_deletion: Turn %s scheduled for deletion at turn %s. Reason: %s",
                 turn.turn_meta["turn"], deletion_turn, deletion_reason)

def apply_pending_deletions(turns_list, current_turn: int, message_logs=None):
    logger.debug("apply_pending_deletions: Entering. Current turn=%s", current_turn)
    for turn in list(turns_list):
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        if turn.tool_meta.get("pending_deletion") and (turn.tool_meta.get("pending_deletion_turn") is not None):
            if current_turn >= turn.tool_meta["pending_deletion_turn"]:
                logger.debug("apply_pending_deletions: Deleting turn %s (tool: %s) at turn %s (scheduled turn: %s).",
                             turn.turn_meta["turn"],
                             turn.tool_meta["tool_name"],
                             current_turn,
                             turn.tool_meta["pending_deletion_turn"])
                if not turn.tool_meta.get("being_deleted", False):
                    turn.tool_meta["being_deleted"] = True
                    turn.delete()
                    turn.tool_meta["being_deleted"] = False
                if message_logs is not None:
                    message_logs.append("Turn {} deleted: {}".format(
                        turn.turn_meta["turn"],
                        turn.tool_meta.get("pending_deletion_reason")))
                turn.tool_meta["pending_deletion"] = False
                turn.tool_meta["pending_deletion_reason"] = None
                turn.tool_meta["pending_deletion_turn"] = None
            else:
                logger.debug("apply_pending_deletions: Turn %s is scheduled for deletion at turn %s (current turn: %s).",
                             turn.turn_meta["turn"], turn.tool_meta["pending_deletion_turn"], current_turn)
    logger.debug("apply_pending_deletions: Completed processing turns.")

def purge_rejected_messages(turns_list, current_turn: int, message_logs=None):
    logger.debug("purge_rejected_messages: Entering (current_turn=%s).", current_turn)
    for turn in turns_list:
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        if turn.tool_meta["rejection"] not in (None, ''):
            logger.debug("purge_rejected_messages: Scheduling deletion for rejected turn %s.", turn.turn_meta["turn"])
            schedule_pending_deletion(turn, current_turn, "Rejected turn removed after delay.")
            if message_logs is not None:
                message_logs.append("Scheduled turn {} for deletion (rejected).".format(turn.turn_meta["turn"]))
    logger.debug("purge_rejected_messages: Completed processing rejected turns.")

def purge_failed_messages(turns_list, current_turn: int, message_logs=None):
    logger.debug("purge_failed_messages: Entering (current_turn=%s).", current_turn)
    for turn in turns_list:
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        status = turn.tool_meta["status"]
        status = status.lower().strip()
        logger.debug("purge_failed_messages: Checking turn %s; status=%s; tool=%s",
                     turn.turn_meta["turn"], status, extract_tool_name(turn))
        if status == "failure":
            logger.debug("purge_failed_messages: Scheduling deletion for failure turn %s.", turn.turn_meta["turn"])
            schedule_pending_deletion(turn, current_turn, "Failure turn removed after delay.")
            if message_logs is not None:
                message_logs.append("Scheduled turn {} for deletion (failure status purge).".format(turn.turn_meta["turn"]))
    logger.debug("purge_failed_messages: Completed processing turns.")

def get_current_tool_message(turns_list, current_tool) -> UnifiedTurn:
    logger.debug("get_current_tool_message: Entering with current_tool=%s.", current_tool.name)
    if not turns_list:
        raise ValueError("Turns list is empty in get_current_tool_message.")
    candidate = turns_list[-1]
    if is_turn0_message(candidate):
        raise ValueError("The last turn is a turn-0 entry, expected a current tool turn.")
    if get_turn_role(candidate) != "tool":
        raise ValueError(f"The last turn (id={candidate.turn_meta['turn']}) is not a tool turn.")
    if extract_tool_name(candidate) != current_tool.name or candidate.tool_meta["rejection"]:
        raise ValueError("The last turn does not match the current tool or is rejected.")
    logger.debug("get_current_tool_message: Found matching tool turn %s.", candidate.turn_meta["turn"])
    return candidate

def get_effective_build_turn(turns_list, current_tool, current_turn: int) -> int:
    logger.debug("get_effective_build_turn: Entering. Current_turn=%s.", current_turn)
    effective_turn = 0
    for turn in turns_list:
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        tool = extract_tool_name(turn)
        if tool in ("tool_build_gradle", "tool_build_test_gradle"):
            msg_turn = turn.turn_meta["turn"]
            if msg_turn > effective_turn:
                effective_turn = msg_turn
                logger.debug("get_effective_build_turn: New effective turn from turn %s = %s.", msg_turn, msg_turn)
    logger.debug("get_effective_build_turn: Final effective build turn=%s.", effective_turn)
    return effective_turn

def purge_until_update_messages(turns_list, current_turn: int, message_logs=None, current_file_key=None):
    logger.debug("purge_until_update_messages: Entering for file key=%s.", current_file_key)
    deletion_reason = "Obsolete until_update turn removed due to file update."
    normalized_current_file_key = os.path.normpath(str(current_file_key)).lower().strip()
    relevant_turns = []
    for turn in turns_list:
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        if turn.tool_meta["deleted"]:
            continue
        msg_policy = normalize_policy(turn.tool_meta["preservation_policy"]).lower().strip()
        if msg_policy == PreservationPolicy.UNTIL_UPDATE.value:
            stored_file_id = turn.tool_meta.get("file_id")
            normalized_stored = os.path.normpath(str(stored_file_id)).lower().strip() if stored_file_id is not None else ""
            if normalized_stored == normalized_current_file_key:
                relevant_turns.append(turn)
                logger.debug("purge_until_update_messages: Found relevant turn %s for file %s.", turn.turn_meta["turn"], normalized_current_file_key)
    if len(relevant_turns) < 2:
        logger.debug("purge_until_update_messages: Only %s relevant turns found; nothing to purge.", len(relevant_turns))
        return
    relevant_turns.sort(key=lambda t: t.turn_meta["turn"])
    latest_turn = relevant_turns[-1]
    logger.debug("purge_until_update_messages: Latest turn is %s.", latest_turn.turn_meta["turn"])
    for turn in relevant_turns:
        if turn.turn_meta["turn"] != latest_turn.turn_meta["turn"] and not turn.tool_meta.get("pending_deletion"):
            logger.debug("purge_until_update_messages: Scheduling deletion for obsolete turn %s.", turn.turn_meta["turn"])
            schedule_pending_deletion(turn, current_turn, deletion_reason)
            if message_logs is not None:
                message_logs.append("Scheduled turn {} for deletion (until_update purge).".format(turn.turn_meta["turn"]))
    logger.debug("purge_until_update_messages: Completed processing turns.")

def purge_one_of_messages(turns_list, current_turn: int, deletion_reason: str, message_logs=None):
    logger.debug("purge_one_of_messages: Purging one-of turns using 'one-of' preservation_policy.")
    eligible = []
    for turn in turns_list:
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        if turn.tool_meta["deleted"] or turn.tool_meta.get("pending_deletion"):
            continue
        if normalize_policy(turn.tool_meta["preservation_policy"]) != PreservationPolicy.ONE_OF.value:
            continue
        eligible.append(turn)
    if not eligible:
        logger.debug("purge_one_of_messages: No eligible one-of turns found.")
        return
    groups = {}
    for turn in eligible:
        tname = extract_tool_name(turn)
        groups.setdefault(tname, []).append(turn)
    for tool, group in groups.items():
        group.sort(key=lambda t: t.turn_meta["turn"], reverse=True)
        newest = group[0]
        logger.debug("purge_one_of_messages: Latest one-of turn for tool '%s' is %s.", 
                     tool, newest.turn_meta["turn"])
        for turn in group[1:]:
            if not turn.tool_meta.get("pending_deletion"):
                logger.debug("purge_one_of_messages: Scheduling deletion for obsolete one-of turn %s (tool: %s).", 
                             turn.turn_meta["turn"], tool)
                schedule_pending_deletion(turn, current_turn, deletion_reason)
                if message_logs is not None:
                    message_logs.append("Scheduled one-of turn {} for deletion (tool: {}).".format(turn.turn_meta["turn"], tool))
    logger.debug("purge_one_of_messages: Completed purging one-of turns.")

def purge_one_time_messages(turns_list, current_turn: int, message_logs=None):
    logger.debug("purge_one_time_messages: Entering (current_turn=%s).", current_turn)
    deletion_reason = "Ephemeral (one-time) turn scheduled for deletion after a 2-turn delay."
    for turn in turns_list:
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        if normalize_policy(turn.tool_meta["preservation_policy"]) == PreservationPolicy.ONE_TIME.value and not turn.tool_meta["deleted"]:
            logger.debug("purge_one_time_messages: Scheduling deletion for one-time turn %s.", turn.turn_meta["turn"])
            schedule_pending_deletion(turn, current_turn, deletion_reason)
            if message_logs is not None:
                message_logs.append("Scheduled one-time turn {} for deletion.".format(turn.turn_meta["turn"]))
    logger.debug("purge_one_time_messages: Completed processing turns.")

def purge_build_messages(turns_list, current_turn: int, message_logs=None):
    logger.debug("purge_build_messages: Starting purge for build turns using 'until-build' preservation_policy.")
    groups = {}
    for turn in turns_list:
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        if normalize_policy(turn.tool_meta["preservation_policy"]) != PreservationPolicy.UNTIL_BUILD.value:
            continue
        if turn.tool_meta["deleted"] or turn.tool_meta["rejection"]:
            logger.debug("purge_build_messages: Skipping turn %s: deleted=%s, rejection=%s",
                         turn.turn_meta["turn"], turn.tool_meta["deleted"], turn.tool_meta["rejection"])
            continue
        tname = extract_tool_name(turn)
        groups.setdefault(tname, []).append(turn)
    for tool, group in groups.items():
        group.sort(key=lambda t: t.turn_meta["turn"])
        for turn in group:
            msg_turn = turn.turn_meta["turn"]
            if msg_turn < current_turn and not turn.tool_meta.get("pending_deletion"):
                logger.debug("purge_build_messages: Scheduling deletion for turn %s (tool '%s') with turn %s < current_turn %s.",
                             turn.turn_meta["turn"], tool, msg_turn, current_turn)
                schedule_pending_deletion(turn, current_turn, "Obsolete build turn purged due to new build execution.")
                if message_logs is not None:
                    message_logs.append("Scheduled build turn {} for deletion (tool: {}).".format(turn.turn_meta["turn"], tool))
        logger.debug("purge_build_messages: Completed processing group for tool '%s'.", tool)
    logger.debug("purge_build_messages: Completed purging build turns.")

def purge_on_tool_execution(current_turn: int, preservation_policy: str, tool_status: str, 
                            turns_list, message_logs=None, current_tool=None, current_file_key=None):
    logger.debug("purge_on_tool_execution: Entered with current_turn=%s, preservation_policy='%s', tool_status='%s'.",
                 current_turn, preservation_policy, tool_status)
    
    set_work_turn = None
    for turn in reversed(turns_list):
        if is_turn0_message(turn):
            continue
        if get_turn_role(turn) != "tool":
            continue
        if extract_tool_name(turn) == "tool_set_work_completed" and not turn.tool_meta["deleted"]:
            set_work_turn = turn
            logger.debug("purge_on_tool_execution: Found set_work_completed turn (id=%s) in history.", turn.turn_meta["turn"])
            break
    
    if set_work_turn is not None:
        current_tool = set_work_turn

    if current_tool is None:
        logger.debug("No current tool provided; skipping purge.")
        return

    norm_tool = current_tool.name
    logger.debug("purge_on_tool_execution: Current tool name is '%s'.", norm_tool)
    
    tool_turn = current_tool

    if tool_turn is not None:
        current_policy = normalize_policy(tool_turn.tool_meta.get("preservation_policy", ""))
        current_rejection = tool_turn.tool_meta.get("rejection", "")
        current_status = tool_turn.tool_meta.get("status", "").lower().strip()
    else:
        current_policy = normalize_policy(getattr(current_tool, "preservation_policy", ""))
        current_rejection = ""
        current_status = ""
    
    if current_policy == PreservationPolicy.ONE_TIME.value or current_rejection not in (None, '',) or current_status == "failure":
        logger.debug("purge_on_tool_execution: Condition 1 met - current tool qualifies for self purge.")
        if tool_turn is not None:
            schedule_pending_deletion(tool_turn, current_turn, "Self purge due to one-time, rejected, or failed status.")
            if message_logs is not None:
                message_logs.append("Scheduled current tool turn {} for self-deletion.".format(tool_turn.turn_meta["turn"]))
        return

    if norm_tool == "tool_purge_chat_turns":
        logger.debug("purge_on_tool_execution: Condition 6 met - current tool is purge_chat_turns; purging specified turns.")
        turns_to_purge = current_tool.tool_meta.get("turns_to_purge")
        if turns_to_purge and isinstance(turns_to_purge, list):
            for turn in turns_list:
                if turn.turn_meta["turn"] in turns_to_purge:
                    schedule_pending_deletion(turn, current_turn, "Purged via purge_chat_turns.")
                    if message_logs is not None:
                        message_logs.append("Scheduled turn {} for deletion (purge_chat_turns).".format(turn.turn_meta["turn"]))
        return

    if norm_tool in ("tool_build_gradle", "tool_build_test_gradle"):
        logger.debug("purge_on_tool_execution: Condition 2 met - current tool is a build tool; purging until-build turns.")
        purge_until_update_messages(turns_list, current_turn, message_logs)
        return

    if norm_tool == "tool_one-of":
        logger.debug("purge_on_tool_execution: Condition 3 met - current tool is one-of; purging prior turns of the same type.")
        purge_one_of_messages(turns_list, current_turn, "Obsolete one-of turn removed due to new one-of tool execution.", message_logs)
        return

    if norm_tool == "tool_write_file":
        logger.debug("purge_on_tool_execution: Condition 4 met - current tool is write_file; purging prior turns with matching filename.")
        if not current_file_key:
            raw_args = tool_turn._messages["tool"]["raw"].get("arguments", "")
            current_file_key = get_normalized_file_key(raw_args)
        if not current_file_key:
            raise ValueError("No file key provided for write_file purge")
        purge_until_update_messages(turns_list, current_turn, message_logs, current_file_key)
        return

    if norm_tool == "tool_set_work_completed":
        logger.debug("purge_on_tool_execution: Condition 5 met - current tool is set_work_completed; purging prior non 'always' and non 'one-of' turns.")
        for turn in turns_list:
            if is_turn0_message(turn):
                continue
            if get_turn_role(turn) != "tool":
                continue
            if turn.turn_meta["turn"] < current_turn:
                turn_policy = normalize_policy(turn.tool_meta.get("preservation_policy", ""))
                if turn_policy not in ("always", PreservationPolicy.ONE_OF.value):
                    logger.debug("purge_on_tool_execution: Purging turn %s under set_work_completed.", turn.turn_meta["turn"])
                    schedule_pending_deletion(turn, current_turn, "Purged due to set_work_completed invocation.")
                    if message_logs is not None:
                        message_logs.append("Scheduled turn {} for deletion (set_work_completed purge).".format(turn.turn_meta["turn"]))
        return

    if norm_tool == "tool_read_file":
        logger.debug("purge_on_tool_execution: Current tool is read_file; no purge triggered.")
        return

    logger.debug("purge_on_tool_execution: Current tool '%s' does not match any purge condition; no purge triggered.", norm_tool)

def get_next_turn_id_from_history(turns_list) -> int:
    next_turn = max((turn.turn_meta["turn"] for turn in turns_list if turn.turn_meta["turn"] != 0), default=0) + 1
    return next_turn

if __name__ == "__main__":
    print("Module turns_purge.py loaded. This module is not intended for direct execution.")
