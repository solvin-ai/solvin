# modules/turns_manager.py

"""
Turn Manager Module

This module orchestrates the conversation loop. It is responsible for:
  • Initializing the conversation history by checking if an initial turn exists.
      - If the history is empty, it invokes prompts.initialize_initial_turn_history to create the initial turn.
  • Repeatedly calling the run_single_turn function from modules.turns_run.py to process each turn.
  • Enforcing a maximum iteration limit.
"""

import time
from modules.logs import logger

def run_conversation_loop():
    """
    Executes the main conversation loop.
    Initializes conversation history if necessary and then repeatedly processes single turns.
    """
    from modules.config import config
    from modules.turns_list import get_turns_list
    from modules.agent_manager import get_running_agent
    from modules.prompts import initialize_initial_turn_history

    agent_role, agent_id = get_running_agent()
    history = get_turns_list(agent_role, agent_id)
    if not history:
        history = initialize_initial_turn_history(history)
    
    max_iterations = int(config.get("MAX_ITERATIONS", "0")) or None
    # Determine the current turn counter based on history.
    turn_counter = max(turn.turn_meta.get("turn", 0) for turn in history) + 1

    from modules.turns_single_run import run_single_turn
    while True:
        turn_counter = run_single_turn()
        logger.info("Processed turn %d", turn_counter - 1)
        if max_iterations is not None and turn_counter >= max_iterations:
            logger.warning("Reached maximum iterations (%d). Exiting.", max_iterations)
            break

    logger.info("Conversation loop ended. Exiting.")

if __name__ == "__main__":
    run_conversation_loop()
