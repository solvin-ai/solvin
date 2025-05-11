# modules/llm.py

"""
This module handles OpenAI API interaction for obtaining assistant responses.
It integrates with the inbound/outbound conversion layers:
  • turns_outbound.py builds the payload (messages only) from the global conversation history.
  • turns_inbound.py converts the raw API response into our standardized internal message structure.

The module provides:
  • get_assistant_response: Prepares the API payload using the conversation history, generates tool metadata
    from the agent-specific tools registry, calls the API, and translates the inbound response via turns_inbound.
  • process_turn: A thin wrapper that takes an agent_role parameter, extracts configuration details,
    and calls get_assistant_response.
"""

from pprint import pformat
from modules.logs import logger
import openai

# Import outbound/inbound conversion functions.
from modules.turns_outbound import build_api_payload
from modules.turns_inbound import parse_api_response

# Import the global tools registry getter.
from modules.tools_registry import get_global_registry
# Import agent_manager to obtain the allowed tools list.
from modules.agent_manager import get_agent_tools
# Import the global turns list getter.
from modules.turns_list import get_turns_list

client = openai

def get_agent_registry(agent_role):
    """
    Retrieves a filtered tools registry for the specified agent type.
    It starts with the global registry and then filters out any tool
    not allowed for this agent.
    
    Returns:
      dict: A dictionary representing the registry schema for only the allowed tools.
    """
    allowed_tools = get_agent_tools(agent_role)
    full_registry = get_global_registry()
    agent_registry = {
        tool_name: tool_info
        for tool_name, tool_info in full_registry.items()
        if tool_name in allowed_tools
    }
    logger.debug("Agent registry for agent_role '%s': %s", agent_role, agent_registry)
    return agent_registry

def get_assistant_response(model, reasoning_effort, agent_role):
    """
    Constructs the API payload from the global conversation history using the agent-specific
    tools registry (which is built independently here), calls the LLM API, and converts the
    raw API response into our internal message structure.
    
    Parameters:
      model (str): The name of the LLM model to use.
      reasoning_effort (str): Specifies the reasoning configuration level for the API.
      agent_role (str): The agent type whose allowed tools registry should be used.
    
    Returns:
      dict: A dictionary with keys "assistant" and "tool" representing the converted messages.
    """
    # Get allowed tools for this agent.
    unified_registry = get_agent_registry(agent_role)
    
    # Build the outbound payload: now only messages are returned.
    payload = build_api_payload()
    messages = payload["messages"]

    # Build tools metadata from the unified_registry.
    # The structure below replicates our past tool metadata shape.
    tools_metadata = []
    for tool_name, tool_obj in unified_registry.items():
        func_def = {
            "name": tool_obj["name"],
            "description": tool_obj["description"],
            "parameters": tool_obj.get("schema", {})  # if absent, default to empty object
        }
        tools_metadata.append({
            "name": tool_name,
            "description": tool_obj["description"],
            "type": "function",
            "function": func_def,
            "parameters": tool_obj.get("schema", {})
        })
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_metadata,  # tools metadata provided from the registry.
            tool_choice="required",
            store=False,
            reasoning_effort=reasoning_effort,
            response_format={"type": "json_object"}
        )
    except openai.BadRequestError as e:
        logger.error("BadRequestError encountered during API call: %s", str(e))
        try:
            turns = get_turns_list()

            # Improved helper that explicitly checks for UnifiedTurn objects.
            def serialize_for_pprint(item, visited=None):
                if visited is None:
                    visited = set()
                try:
                    obj_id = id(item)
                except Exception:
                    obj_id = None
                if obj_id is not None and obj_id in visited:
                    return f"<Circular reference to {type(item).__name__}>"
                if obj_id is not None:
                    visited.add(obj_id)
                if isinstance(item, list):
                    return [serialize_for_pprint(sub, visited) for sub in item]
                if isinstance(item, dict):
                    return {k: serialize_for_pprint(v, visited) for k, v in item.items()}
                if type(item).__name__ == "UnifiedTurn":
                    turn_meta = getattr(item, "turn_meta", "<MISSING>")
                    tool_meta = getattr(item, "tool_meta", "<MISSING>")
                    messages = getattr(item, "messages", "<MISSING>")
                    return {"__UnifiedTurn__": {
                        "turn_meta": serialize_for_pprint(turn_meta, visited),
                        "tool_meta": serialize_for_pprint(tool_meta, visited),
                        "messages": serialize_for_pprint(messages, visited)
                    }}
                if hasattr(item, "__dict__"):
                    return serialize_for_pprint(item.__dict__, visited)
                return item

            dumped_turns = pformat(serialize_for_pprint(turns), indent=2)
            logger.error("Complete recursive turns list dump:\n%s", dumped_turns)
        except Exception as dump_err:
            logger.error("Error dumping turns list: %s", str(dump_err))
        raise

    raw_message = completion.choices[0].message.to_dict()
    return parse_api_response({"assistant": raw_message})

def process_turn(config_dict, agent_role):
    """
    Extracts configuration details and invokes get_assistant_response using the agent-specific tools registry.
    
    Parameters:
      config_dict (dict): Configuration dictionary (expects keys "LLM_MODEL" and "LLM_REASONING_LEVEL").
      agent_role (str): The agent type to determine the subset of tools to use.
    
    Returns:
      dict: The converted API response with keys "assistant" and "tool".
    """
    model = config_dict.get("LLM_MODEL")
    reasoning_effort = config_dict.get("LLM_REASONING_LEVEL", "high")
    return get_assistant_response(model, reasoning_effort, agent_role)

if __name__ == "__main__":
    test_config = {"LLM_MODEL": "gpt-4", "LLM_REASONING_LEVEL": "high"}
    test_agent_role = "root"
    try:
        response = process_turn(test_config, test_agent_role)
        logger.info("Assistant response: %s", pformat(response))
    except Exception as e:
        logger.error("Error during API call: %s", str(e))
