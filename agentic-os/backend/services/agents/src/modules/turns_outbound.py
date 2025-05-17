# modules/turns_outbound.py

"""
Transforms internal conversation history (a list of UnifiedTurn objects)
into outbound messages ready for the OpenAI Chat API.

In the updated version, messages with an internal role "tool"
are sent with the role "tool" (not "function", which is now deprecated).

All history lookups are now scoped by the full
(agent_role, agent_id, repo_url) quartet.

Deleted turns (tool_meta['deleted']==True) are now skipped entirely,
except for turn‐0 which is always included.
"""

from modules.unified_turn import UnifiedTurn
from modules.turns_list   import get_turns_list
from modules.agents_running import get_current_agent_tuple as get_current_agent


def _normalize_raw_message(raw: dict, tool_name: str) -> dict:
    """
    Normalize a raw message dict for outbound API use.

    With the updated OpenAI API, tool messages are now represented with the role "tool"
    instead of converting them to "function". This function returns a shallow copy of the raw
    message without modifying its role.
    """
    api_msg = raw.copy()
    return api_msg


def get_outbound_messages(history: list[UnifiedTurn]) -> list[dict]:
    """
    Flatten a list of UnifiedTurn objects into a list of outbound message
    dictionaries suitable for the OpenAI Chat API.

    Skips any turn >=1 marked deleted (tool_meta['deleted']==True).
    Turn‐0 is always included and may contain multiple roles.
    """
    outbound_messages: list[dict] = []

    for turn in history:
        turn_idx = turn.turn_meta.get("turn", None)

        # skip any non‐zero turn marked deleted
        if turn_idx is not None and turn_idx != 0 and turn.tool_meta.get("deleted", False):
            continue

        # extract tool_name for normalization, if available
        tool_name = ""
        if isinstance(turn.tool_meta, dict):
            tool_name = turn.tool_meta.get("tool_name", "")

        # iterate over all roles in this turn
        for msg in turn.messages.values():
            if isinstance(msg, dict) and "raw" in msg:
                normalized = _normalize_raw_message(msg["raw"], tool_name)
                outbound_messages.append(normalized)
            else:
                # in case we stored a pre‐normalized dict
                outbound_messages.append(msg)

    return outbound_messages


def build_api_payload() -> dict:
    """
    Build the API payload for the OpenAI Chat API by converting the current
    conversation history into a list of outbound-ready message dictionaries.

    Returns:
      dict: { "messages": [...] }
    """
    # Determine the current agent from thread-local context
    role, agent_id, repo_url = get_current_agent()
    if not role:
        raise RuntimeError("No current-agent in context when building API payload")

    # Load the history
    history = get_turns_list(role, agent_id, repo_url)

    # Flatten into API-ready messages (skipping deleted turns)
    messages = get_outbound_messages(history)
    return {"messages": messages}


def convert_unified_turn_to_api_message(unified_turn: UnifiedTurn) -> dict:
    """
    Convert a single UnifiedTurn object into a dict for debugging,
    retaining its turn_meta, tool_meta, and messages.
    """
    return {
        "turn_meta": unified_turn.turn_meta,
        "tool_meta": unified_turn.tool_meta,
        "messages":  unified_turn.messages,
    }


if __name__ == "__main__":
    # Demo / smoke test
    import json
    from modules.agents_running import set_thread_current_agent_tuple as set_current_agent

    set_current_agent("root", "001", "demo_repo")

    payload = build_api_payload()
    print("Outbound API Payload:")
    print(json.dumps(payload, indent=2))

    example_turn = get_turns_list("root", "001", "demo_repo")[0]
    api_msg = convert_unified_turn_to_api_message(example_turn)
    print("\nConverted UnifiedTurn:")
    print(json.dumps(api_msg, indent=2))
