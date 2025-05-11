# modules/turns_manager.py

"""
Turn Manager Module

Orchestrates the conversation loop. Responsible for:
  • Initializing the conversation history if needed (using initial prompt/turn).
  • Repeatedly invoking run_single_turn from modules.turns_single_run to process each conversation turn.
  • Enforcing a maximum iteration limit.
"""

import time
from shared.logger import logger

def run_conversation_loop():
    from shared.config import config
    from modules.turns_list import get_turns_list
    from modules.agents_running import get_current_agent_tuple
    from modules.prompts import initialize_initial_turn_history

    agent_role, agent_id = get_current_agent_tuple()
    history = get_turns_list(agent_role, agent_id)
    if not history:
        history = initialize_initial_turn_history(history)

    max_iterations = int(config.get("MAX_ITERATIONS", "0")) or None
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
