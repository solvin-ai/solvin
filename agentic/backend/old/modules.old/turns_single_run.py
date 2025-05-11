# modules/turns_single_run.py

"""
Turn Run Module

This module is responsible for processing a single conversation turn.
The run_single_turn function performs the following tasks:
  • Initializes context by loading configuration, agent details, and other settings.
  • Retrieves the conversation history (which should already contain an initial turn).
  • Determines the current turn number.
  • Checks if the accumulated context size exceeds the threshold specified in config.
    If a violation is detected, triggers an interactive pause and increments the turn counter.
  • If no violation is detected:
         - Invokes the LLM (via llm.process_turn) to obtain the assistant's response, measuring execution time.
         - Delegates processing of the assistant turn (and any tool calls) to turns_processor.handle_assistant_turn.
         - Updates UI components via modules.ui_tables.
         - Persists the conversation history if the latest turn has been finalized.
         - Triggers an interactive pause.
  • Returns the updated turn counter.
"""

import time

from modules.turns_processor import handle_context_violation, handle_assistant_turn
from modules.llm import process_turn
from modules.ui_tables import print_all_tables
from modules.turns_list import save_and_purge_turns_list, get_turns_list
from modules.cli import interactive_pause
from modules.logs import logger


def initialize_context():
    """
    Initializes and returns context configuration and agent details.

    Returns:
      tuple: (config, agent_role, agent_id, host_repos, repo_name, run_in_container, max_iterations)
    """
    from modules.config import config
    from modules.agent_manager import get_running_agent

    agent_role, agent_id = get_running_agent()
    host_repos = config.get("HOST_REPOS", ".")
    repo_name = config.get("REPO_NAME", scope="service.repos")
    run_in_container = str(config.get("RUN_TOOLS_IN_CONTAINER", "false")).lower() in ("true", "1", "yes")
    max_iterations = int(config.get("MAX_ITERATIONS", "0")) or None

    return config, agent_role, agent_id, host_repos, repo_name, run_in_container, max_iterations


def run_single_turn() -> int:
    """
    Processes a single conversation turn.

    Responsibilities:
      • Initializes context and retrieves conversation history.
      • Ensures the conversation history contains an initial turn; if empty, raises an error.
      • Determines the current turn number.
      • Checks if the accumulated context size exceeds the threshold specified in config.
        If a violation is detected, triggers an interactive pause and increments the turn counter.
      • If no violation is detected:
           - Invokes the LLM to obtain the assistant's response while measuring execution time.
           - Delegates processing of the assistant turn (and any tool calls) to turns_processor.handle_assistant_turn.
           - Updates the UI via modules.ui_tables.
           - Persists the conversation history if the latest turn has been finalized.
           - Triggers an interactive pause.
      • Returns the updated turn counter.
    """
    # Initialize context and configuration.
    config, agent_role, agent_id, host_repos, repo_name, run_in_container, max_iterations = initialize_context()

    # Retrieve conversation history.
    history = get_turns_list(agent_role, agent_id)
    if not history:
        logger.error("Conversation history is empty. The initial turn should be created in turns_manager.")
        raise Exception("Initial turn missing. Please create it in turns_manager.")

    # Determine the current turn counter.
    turn_counter = max(turn.turn_meta.get("turn", 0) for turn in history) + 1

    # Check for context violation.
    violation_detected = handle_context_violation(
        turns_list=history,
        config=config,
        current_turn=turn_counter,
        agent_role=agent_role,
        agent_id=agent_id,
        interactive_pause_fn=interactive_pause,
        save_fn=save_and_purge_turns_list
    )
    if violation_detected:
        logger.warning("Context violation detected at turn %s", turn_counter)
        time.sleep(0.1)
        return turn_counter + 1

    # Invoke the LLM to obtain the assistant's response.
    start_time = time.time()
    assistant_response = process_turn(config, agent_role)
    end_time = time.time()
    execution_time = end_time - start_time

    # Process the assistant turn.
    handle_assistant_turn(assistant_response, turn_counter, history, execution_time)

    # Update the UI.
    print_all_tables()

    # Persist conversation history if the latest turn is finalized.
    if history and history[-1].turn_meta.get("finalized", False):
        save_and_purge_turns_list(agent_role, agent_id)

    # Trigger an interactive pause.
    interactive_pause(turn_counter)

    logger.info("Processed turn %d", turn_counter)
    return turn_counter + 1
