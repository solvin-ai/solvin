# modules/turns_single_run.py

"""
This module executes one turn: it loads the history, builds the outbound messages, constructs
the tools metadata (using the updated structure for the new tools API), makes the API call,
processes the assistant response (and any tool calls), renders UI tables, and finally persists
and clears history if complete.

Note: With OpenAI having deprecated the legacy "functions" API in favor of "tools",
this file now constructs the tools metadata in the updated format and passes explicit
repo_owner/repo_name parameters through to the processor (instead of embedding repo_url
in execute_tool).
"""

import time
from typing import Optional

from shared.logger import logger
from shared.config import config

from modules.turns_list import get_turns_list, save_and_purge_turns_list
from modules.turns_outbound import get_outbound_messages
from modules.messages_llm import get_assistant_response
from modules.turns_processor import handle_assistant_turn
from modules.ui_tables import print_all_tables


def run_single_turn(
    agent_role:       str,
    agent_id:         str,
    repo_url:         str,
    unified_registry: dict,
    repo_owner:       Optional[str] = None,
    repo_name:        Optional[str] = None
) -> int:
    """
    Execute one LLM + tool invocation turn:
      1) Load conversation history.
      2) Compute the next turn index.
      3) Prepare and send an LLM request.
      4) Process the assistant response and any tool calls.
      5) Render UI tables.
      6) Persist & clear history if finalized.
      7) Return the next turn index.

    repo_owner and repo_name are passed explicitly for downstream tool execution.
    """
    # 1) Load history
    history = get_turns_list(agent_role, agent_id, repo_url)
    if not history:
        raise RuntimeError("Missing initial turn; please initialize history before running turns.")

    # 2) Compute this turn number
    turn_counter = max(t.turn_meta.get("turn", 0) for t in history) + 1

    # 3a) Choose the LLM model
    model = config.get("LLM_MODEL", default="gpt-4")

    # 3b) Build the outbound messages payload
    messages = get_outbound_messages(history)

    # 3c) Build tools metadata using the updated tools API structure.
    #     The new format replaces the legacy "functions" style.
    if isinstance(unified_registry, dict):
        registry_values = unified_registry.values()
    else:
        registry_values = unified_registry

    tools_metadata = []
    for tool in registry_values:
        tools_metadata.append({
            "type": "function",
            "function": {
                "name":        tool["name"],
                "description": tool["description"],
                "parameters":  tool.get("schema", {})  # defaults to {} if missing
            }
        })

    # 3d) Call the LLM API with the assembled messages and tools metadata.
    start = time.time()
    logger.debug("Turn %d: sending LLM request with %d messages and %d tools",
                 turn_counter, len(messages), len(tools_metadata))
    assistant_response = get_assistant_response(
        model=model,
        messages=messages,
        tools_metadata=tools_metadata,
        tool_choice=config.get("TOOL_CHOICE", default="required"),
    )
    execution_time = time.time() - start

    # 4) Process the assistant response (and any tool calls), passing repo_owner/repo_name
    handle_assistant_turn(
        assistant_response=assistant_response,
        turn_counter=turn_counter,
        history=history,
        execution_time=execution_time,
        unified_registry=unified_registry,
        agent_role=agent_role,
        agent_id=agent_id,
        repo_url=repo_url,
        repo_owner=repo_owner,
        repo_name=repo_name
    )

    # 5) Render UI tables
    print_all_tables()

    # 6) If the last turn is finalized, persist and clear history.
    if history and history[-1].turn_meta.get("finalized", False):
        save_and_purge_turns_list(agent_role, agent_id, repo_url)

    # 7) Return the next turn index.
    return turn_counter + 1


if __name__ == "__main__":
    # For local testing / demo purposes.
    unified_registry_demo = {
        "tool_directory_tree": {
            "name": "tool_directory_tree",
            "description": "Generates a directory tree representation.",
            "schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The directory path."
                    },
                    "max_depth": {
                        "type": "number",
                        "description": "Maximum depth for directory recursion."
                    }
                },
                "required": ["path"]
            }
        }
    }

    AGENT_ROLE = "example_role"
    AGENT_ID   = "agent_123"
    REPO_URL   = "sample_repo"

    # Supply dummy owner/name for testing repo_owner/repo_name forwarding.
    next_turn = run_single_turn(
        agent_role=AGENT_ROLE,
        agent_id=AGENT_ID,
        repo_url=REPO_URL,
        unified_registry=unified_registry_demo,
        repo_owner="my-org",
        repo_name="my-repo"
    )
    print("Next turn index:", next_turn)
