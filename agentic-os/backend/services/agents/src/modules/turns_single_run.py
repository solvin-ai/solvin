# modules/turns_single_run.py

"""
This module executes one turn: it loads the history, builds the outbound messages, constructs
the tools metadata (using the updated structure for the new tools API), makes the API call,
processes the assistant response (and any tool calls), renders UI tables, and finally persists
and clears history if complete.

Now fully scoped to (agent_role, agent_id, repo_url).  repo_owner/repo_name are
passed through for downstream tool execution.
"""

import time
from typing import Optional

from shared.logger import logger
from shared.config import config

from modules.turns_list import (
    get_turns_list,
    save_turns_list
)
from modules.turns_outbound  import get_outbound_messages
from modules.messages_llm    import get_assistant_response
from modules.turns_processor import handle_assistant_turn
from modules.ui_tables       import print_all_tables


def run_single_turn(
    agent_role:       str,
    agent_id:         str,
    repo_url:         str,
    unified_registry: dict,
    model:            str,            # <--- now required
    repo_owner:       Optional[str] = None,
    repo_name:        Optional[str] = None,
    reasoning_effort: Optional[str] = None,
) -> int:
    """
    Execute one LLM + tool invocation turn:
      1) Load conversation history.
      2) Compute the next turn index.
      3) Use the provided LLM model and prepare request.
      4) Process the assistant response and any tool calls.
      5) Render UI tables.
      6) Persist & clear history if finalized.
      7) Return the next turn index.

    All calls are now scoped by (agent_role, agent_id, repo_url).
    """

    # 1) Load history
    history = get_turns_list(agent_role, agent_id, repo_url)
    if not history:
        raise RuntimeError("Missing initial turn; please initialize history before running turns.")

    # 2) Compute this turn number
    turn_counter = max(t.turn_meta.get("turn", 0) for t in history) + 1

    # 3a) The LLM model is passed in as the `model` parameter

    # 3b) Build the outbound messages payload
    messages = get_outbound_messages(history)

    # 3c) Build tools metadata using the updated tools API structure.
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

    # 3d) Call the LLM API
    start = time.time()
    logger.debug(
        "Turn %d: sending LLM request with %d messages and %d tools using model=%s (reasoning_effort=%s)",
        turn_counter, len(messages), len(tools_metadata), model, reasoning_effort
    )
    assistant_response = get_assistant_response(
        model=model,
        messages=messages,
        tools_metadata=tools_metadata,
        tool_choice=config.get("TOOL_CHOICE", default="required"),
        reasoning_effort=reasoning_effort,
    )
    execution_time = time.time() - start

    # 4) Process the assistant response (and any tool calls)
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
        save_turns_list(agent_role, agent_id, repo_url)

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
    MODEL      = "gpt-4"   # <--- specify the model here

    next_turn = run_single_turn(
        agent_role=AGENT_ROLE,
        agent_id=AGENT_ID,
        repo_url=REPO_URL,
        unified_registry=unified_registry_demo,
        model=MODEL,
        repo_owner="my-org",
        repo_name="my-repo",
        reasoning_effort="high"
    )
    print("Next turn index:", next_turn)
