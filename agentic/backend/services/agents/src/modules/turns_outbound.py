# modules/turns_outbound.py

"""
Transforms internal conversation history (a list of UnifiedTurn objects)
into outbound messages ready for the OpenAI Chat API.

In the updated version (as of mid-2024 and beyond), messages with an internal role "tool"
are sent with the role "tool" (not "function", which is now deprecated).

Other messages are simply extracted from their “raw” property.
"""

from modules.unified_turn import UnifiedTurn
from modules.turns_list import get_turns_list
from modules.agent_context import get_current_agent


def _normalize_raw_message(raw: dict, tool_name: str) -> dict:
    """
    Normalize a raw message dict for outbound API use.

    With the updated OpenAI API, tool messages are now represented with the role "tool"
    instead of converting them to "function". This function returns a shallow copy of the raw
    message without modifying its role.

    (The 'json' module is used later for pretty-printing in our demo.)

    Parameters:
      raw (dict): a raw message dictionary from a UnifiedTurn.
      tool_name (str): the name associated with the tool (or empty string).

    Returns:
      dict: the normalized message dictionary.
    """
    api_msg = raw.copy()
    # In the updated system, we do not change role "tool" to "function".
    # If needed, additional properties (e.g., tool_call_id) can be injected here.
    return api_msg


def get_outbound_messages(history: list[UnifiedTurn]) -> list[dict]:
    """
    Flatten a list of UnifiedTurn objects into a list of outbound message
    dictionaries suitable for the OpenAI Chat API.

    For each turn, extract the "raw" sub-dictionary from every message.
    Tool messages are passed through without modification.

    Parameters:
      history (list): List of UnifiedTurn objects.

    Returns:
      list: Outbound message dictionaries.
    """
    outbound_messages: list[dict] = []
    for turn in history:
        # Extract the tool name from turn_meta if present
        tool_name = ""
        if isinstance(turn.tool_meta, dict):
            tool_name = turn.tool_meta.get("tool_name", "")

        for msg in turn.messages.values():
            if isinstance(msg, dict) and "raw" in msg:
                normalized = _normalize_raw_message(msg["raw"], tool_name)
                outbound_messages.append(normalized)
            else:
                outbound_messages.append(msg)
    return outbound_messages


def build_api_payload() -> dict:
    """
    Build the API payload for the OpenAI Chat API by converting the current
    conversation history into a list of outbound-ready message dictionaries.

    Returns:
      dict: A dictionary with a "messages" key containing the messages.
    """
    # Determine the current agent from context
    role, agent_id, repo_url = get_current_agent()
    if not role:
        raise RuntimeError("No current-agent in context when building API payload")

    # Load the history (turn-0 is guaranteed by get_turns_list)
    history = get_turns_list(role, agent_id, repo_url)

    # Flatten into API-ready messages
    messages = get_outbound_messages(history)
    return {"messages": messages}


def convert_unified_turn_to_api_message(unified_turn: UnifiedTurn) -> dict:
    """
    Convert a single UnifiedTurn object into a dictionary for API debugging,
    retaining its turn_meta, tool_meta, and messages.

    Parameters:
      unified_turn: A UnifiedTurn object.

    Returns:
      dict: Dictionary representation of the UnifiedTurn.
    """
    return {
        "turn_meta": unified_turn.turn_meta,
        "tool_meta": unified_turn.tool_meta,
        "messages":  unified_turn.messages,
    }


if __name__ == "__main__":
    # Demo/smoke test
    import json

    # Fake an agent context for testing
    from modules.agent_context import set_current_agent
    set_current_agent("root", "001", "demo_repo")

    payload = build_api_payload()
    print("Outbound API Payload:")
    print(json.dumps(payload, indent=2))

    # Example usage of convert_unified_turn_to_api_message
    example_turn = get_turns_list("root", "001", "demo_repo")[0]
    api_msg = convert_unified_turn_to_api_message(example_turn)
    print("\nConverted UnifiedTurn:")
    print(json.dumps(api_msg, indent=2))
