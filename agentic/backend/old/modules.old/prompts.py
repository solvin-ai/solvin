# modules/prompts.py

"""
This module handles retrieving the initial prompts (developer and user) and processing the repository JDK logic.
It is responsible for:
  • Detecting the repository JDK version.
  • Switching to the required JDK version if needed.
  • Setting the JDK_VERSION environment variable.
  • Fetching and preparing the developer and user prompts.
"""

import os

from modules.detect_repo import detect_jdk_version
from modules.jdk import switch_jdk_and_validate
from modules.agent_manager import get_agent_prompts
from modules.logs import logger


def setup_initial_prompts(config, agent_role, host_repos, repo_name, run_in_container):
    """
    Sets up the initial prompts and processes repository JDK logic.

    Parameters:
      config         - The configuration object/dictionary.
      agent_role     - The type of agent in use.
      host_repos     - The base directory for repositories.
      repo_name      - The name of the repository.
      run_in_container - Boolean; True if the system is running in a container environment.

    Returns:
      A tuple (dev_prompt, usr_prompt, detected_jdk)
    """
    # Determine the repository path to use for JDK detection.
    if run_in_container:
        repo_for_detection = os.path.abspath(repo_name)
    else:
        repo_for_detection = os.path.join(host_repos, repo_name)

    # Detect the repository's JDK version.
    detected_jdk = detect_jdk_version(repo_for_detection) or "unknown"
    logger.line(style=1)
    logger.info("Detected repository JDK version: %s", detected_jdk)

    # If a valid JDK version was detected, switch to it.
    if detected_jdk != "unknown":
        logger.info("Switching to required JDK version (%s)...", detected_jdk)
        switch_jdk_and_validate(detected_jdk)
    else:
        logger.warning("Could not determine a valid JDK version from repository metadata.")

    # Set the JDK version in the environment.
    os.environ["JDK_VERSION"] = detected_jdk

    # Fetch the developer and user prompts from the agent manager.
    dev_prompt, usr_prompt = get_agent_prompts(agent_role)
    if not dev_prompt:
        dev_prompt = config.get("LLM_SYSTEM_PROMPT") or "No developer prompt set"
    if not usr_prompt:
        usr_prompt = config.get("LLM_USER_PROMPT") or "No user prompt set"

    # Replace any placeholder for the JDK version in the user prompt.
    usr_prompt = usr_prompt.replace("{JDK_VERSION}", detected_jdk)

    return dev_prompt, usr_prompt, detected_jdk


def create_initial_turn(config, agent_role, host_repos, repo_name, run_in_container):
    """
    Creates the initial (turn-0) conversation turn with system, developer, and user messages.

    Parameters:
      config         - The configuration object/dictionary.
      agent_role     - The type of agent in use.
      host_repos     - The base directory for repositories.
      repo_name      - The name of the repository.
      run_in_container - Boolean; True if the system is running in a container environment.

    Returns:
      A UnifiedTurn object representing the initial turn.
    """
    from modules.unified_turn import UnifiedTurn

    dev_prompt, usr_prompt, detected_jdk = setup_initial_prompts(config, agent_role, host_repos, repo_name, run_in_container)
    logger.line(style=1)
    system_content = (
        "Please respond with a valid json object. "
        "Make sure your response includes the word 'json' in some form."
    )
    initial_meta = {
        "turn": 0,
        "total_char_count": len(system_content) + len(dev_prompt) + len(usr_prompt),
        "finalized": True,
        "tool_meta": {
            "status": "",
            "execution_time": 0,
            "deleted": False,
            "rejection": None,
        }
    }
    initial_raw_messages = {
        "system": {"raw": {"role": "system", "content": system_content}},
        "developer": {"raw": {"role": "developer", "content": dev_prompt}},
        "user": {"raw": {"role": "user", "content": usr_prompt}}
    }
    return UnifiedTurn.create_turn(initial_meta, initial_raw_messages)


def initialize_initial_turn_history(history):
    """
    Initializes the conversation history with the initial (turn-0) turn if the history is empty.
    This function retrieves the necessary configuration and agent details, creates the initial turn,
    appends it to the provided history, and logs the turn messages.

    Parameters:
      history - The existing conversation history list to be updated.

    Returns:
      The updated conversation history list with the initial turn appended.
    """
    from modules.config import config
    from modules.agent_manager import get_running_agent

    agent_role, _ = get_running_agent()
    host_repos = config.get("HOST_REPOS", ".")
    repo_name = config.get("REPO_NAME", scope="service.repos")
    run_in_container = str(config.get("RUN_TOOLS_IN_CONTAINER", "false")).lower() in ("true", "1", "yes")
    init_turn = create_initial_turn(config, agent_role, host_repos, repo_name, run_in_container)
    history.append(init_turn)
    logger.info("Dumping initial turn (turn 0) messages:")
    for role, msg in init_turn.messages.items():
        content = msg.get("raw", {}).get("content", "")
        logger.info("Role: %s, Content: %s", role, content)
    return history
