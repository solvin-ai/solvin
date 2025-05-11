# tools/tool_purge_chat_turns.py

import os

from shared.config import config
from shared.logger import logger

from modules.tools_safety import (
    get_repos_dir,
    get_log_dir,
    get_repo_path,
    resolve_repo_path,
    check_path,
    mask_output,
)

def tool_purge_chat_turns(turns: list) -> dict:
    """
    Purges chat turns specified by a list of turn numbers.

    Parameters:
      turns (list): A list of integers representing the turn numbers.

    Returns:
      dict: A dictionary with keys:
            - "success": a boolean flag indicating whether the purging was successful,
            - "output": a message describing the result.
    """
    # sandbox safety: ensure we’re inside the allowed repo
    repo = config["REPO_NAME"]
    repo_root = get_repo_path(repo)
    check_path(repo_root)

    logger.debug("tool_purge_chat_turns invoked, current working directory: %s", os.getcwd())
    try:
        if not isinstance(turns, list):
            raise TypeError(f"Expected a list of turn numbers, got {type(turns)}")
        for turn in turns:
            if not isinstance(turn, int):
                raise ValueError(f"All turn numbers must be integers, found: {turn} ({type(turn)})")

        logger.info("Purging turns: %s", turns)
        output = f"Purged turns: {turns}"
        return {
            "success": True,
            "output": mask_output(output),
        }
    except Exception as e:
        logger.exception("Error purging chat turns: %s", e)
        return {
            "success": False,
            "output": mask_output(str(e)),
        }

def get_tool():
    """
    Returns the tool specification for purging chat turns.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_purge_chat_turns",
            "description": "Purges specified chat turns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "turns": {
                        "type": "array",
                        "description": "List of turn numbers to purge.",
                        "items": {"type": "integer"},
                    },
                },
                "required": ["turns"],
                "additionalProperties": False,
                "strict": True,
            },
        },
        "internal": {
            "preservation_policy": "one-time",
            "type": "readonly",
        },
    }
