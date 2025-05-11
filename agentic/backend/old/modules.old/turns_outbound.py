# modules/turns_outbound.py

"""
Updated turns_outbound.py

This module transforms the internal conversation history (a list of UnifiedTurn objects)
into outbound data formatted for the LLM API.

Since our system guarantees that the "raw" messages are already JSON‐ready and that every
message has its "content" defined properly, we simply extract and pass them along.
Also, any tool metadata is already stored within each turn under the "tool_meta" key.
"""

def get_outbound_messages(history):
    """
    Iterates over the conversation history (a list of UnifiedTurn objects)
    and extracts outbound messages for the LLM API.

    Since each message's "raw" field is already fully formatted, we simply copy
    that data without any modifications.

    Parameters:
      history (list): The conversation history, obtained from modules.turns_list.get_turns_list().

    Returns:
      list: A list of outbound message dictionaries.
    """
    outbound_messages = []
    for turn in history:
        for role, msg in turn.messages.items():
            if isinstance(msg, dict) and "raw" in msg:
                outbound_messages.append(msg["raw"].copy())
            else:
                outbound_messages.append(msg)
    return outbound_messages

def build_api_payload():
    """
    Constructs the payload to be sent to the LLM API. Since our system already
    handles proper JSON formatting, this function simply:
      - Retrieves the conversation history.
      - Extracts the outbound messages as-is.
    
    No tool metadata is added because the API relies solely on these raw messages.

    Returns:
      dict: A payload dictionary with a 'messages' key.
    """
    # Retrieve the conversation history via the centralized function.
    from modules.turns_list import get_turns_list
    history = get_turns_list()
    outbound_messages = get_outbound_messages(history)
    return {"messages": outbound_messages}

def convert_unified_turn_to_api_message(unified_turn):
    """
    Converts a single UnifiedTurn object into an API‑ready dictionary.
    
    The output includes:
      - "turn_meta": Turn-specific metadata.
      - "tool_meta": Tool metadata (stored during processing), even if the API doesn't require it.
      - "messages" : The raw messages intended for the API.
    
    Parameters:
      unified_turn (UnifiedTurn): A turn object.
      
    Returns:
      dict: The API‑ready representation of the turn.
    """
    return {
        "turn_meta": unified_turn.turn_meta,
        "tool_meta": unified_turn.tool_meta,
        "messages": unified_turn.messages
    }

if __name__ == "__main__":
    # Basic testing stub.
    # For testing purposes, we create a dummy UnifiedTurn-like object.
    class DummyTurn:
        def __init__(self, messages, tool_meta, turn_meta):
            self._messages = messages
            self._tool_meta = tool_meta
            self._turn_meta = turn_meta

        @property
        def messages(self):
            return self._messages

        @property
        def tool_meta(self):
            return self._tool_meta

        @property
        def turn_meta(self):
            return self._turn_meta

    # Create dummy turns with preformatted raw messages.
    turn0 = DummyTurn(
        messages={
            "assistant": {"raw": {
                "role": "assistant",
                "content": "Hello, this is the assistant message.",
                "extra_field": "preserve_this"
            }},
            "tool": {"raw": {
                "role": "tool",
                "content": '{"result": "OK", "details": "Tool response"}',
                "name": "example_tool"
            }}
        },
        tool_meta={"tool_name": "example_tool"},
        turn_meta={"turn": 0, "finalized": True, "total_char_count": 120}
    )

    turn1 = DummyTurn(
        messages={
            "assistant": {"raw": {
                "role": "assistant",
                "content": "Processing complete."
            }}
        },
        tool_meta={},
        turn_meta={"turn": 1, "finalized": True, "total_char_count": 50}
    )
    
    # Simulate an in-memory conversation history.
    dummy_history = [turn0, turn1]
    
    # Temporarily override get_turns_list for testing purposes.
    def get_turns_list_override():
        return dummy_history

    import types
    get_turns_list = types.FunctionType(get_turns_list_override.__code__, globals())
    
    # Build the outbound payload.
    import json
    payload = build_api_payload()
    print("Outbound Payload:")
    print(json.dumps(payload, indent=2))
    
    # Test conversion of a single UnifiedTurn to an API message.
    api_msg = convert_unified_turn_to_api_message(turn0)
    print("\nUnifiedTurn (converted to API message):")
    print(json.dumps(api_msg, indent=2))
