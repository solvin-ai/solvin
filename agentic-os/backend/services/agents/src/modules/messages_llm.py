# modules/messages_llm.py

"""
LLM orchestration: single‐turn only.
Accepts fully prepared message history and tool metadata, invokes OpenAI,
and parses the JSON function‐call response into our AssistantResponse shape.
"""

from typing import Any, Dict, List, Optional
from openai import OpenAI
from shared.logger import logger
from modules.turns_inbound import parse_api_response

client = OpenAI()


def get_assistant_response(
    model: str,
    messages: List[Dict[str, Any]],
    tools_metadata: List[Dict[str, Any]],
    tool_choice: str = "auto",
    reasoning_effort: Optional[str] = None
) -> Dict[str, Any]:
    """
    Call OpenAI.preview chat.completions.create with:
      • model
      • messages: full chat history (with turn-0 already prepended)
      • tools: list of { "type":"function", "function":{…} } entries
      • tool_choice: "auto" or {"name": "..."}
      • reasoning_effort: optional override

    Returns:
      A dict containing keys:
        - "assistant": wrapped assistant message (raw+meta)
        - "tools":      list of wrapped tool messages
        - "tools_meta": list of metadata dicts (one per tool_call)
        - "total_char_count": int, sum of all char_counts in assistant+tools
    """
    api_kwargs: Dict[str, Any] = {
        "model":       model,
        "messages":    messages,
        "tools":       tools_metadata,
        "tool_choice": tool_choice,
    }

    if reasoning_effort is not None:
        api_kwargs["reasoning_effort"] = reasoning_effort
    else:
        logger.debug("No reasoning_effort provided for model '%s'", model)

    #logger.debug(
    #    "Calling preview client.chat.completions.create with:\n%s",
    #    api_kwargs
    #)
    completion = client.chat.completions.create(**api_kwargs)

    raw_message = completion.choices[0].message.to_dict()
    logger.debug("Received raw LLM message: %s", raw_message)

    # Parse raw function‐call JSON into our internal AssistantResponse format
    return parse_api_response({"assistant": raw_message})
