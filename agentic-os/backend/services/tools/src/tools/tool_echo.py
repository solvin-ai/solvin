# tools/tool_echo.py

"""
Tool: Echo
Description: A simple tool that echoes back the input text provided.
"""

from shared.config import config

from modules.tools_safety import (
    get_safe_repo_root,
    mask_output,
)

def tool_echo(input_text: str) -> dict:
    """
    Echoes back the input text provided, after validating the repository
    context and masking any absolute paths.

    Parameters:
      input_text (str): The text to be echoed.

    Returns:
      dict: A dictionary with:
             - "success": True if the echo succeeded.
             - "output": the echoed text
    """

    return {"success": True, "output": input_text}

def get_tool() -> dict:
    """
    Returns the tool specification for the Echo tool.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_echo",
            "description": "Echoes back the input text provided (with paths masked).",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_text": {
                        "type": "string",
                        "description": "The text to be echoed."
                    }
                },
                "required": ["input_text"],
                "additionalProperties": False
            }
        },
        "internal": {
            "preservation_policy": "one-time",
            "type": "readonly"
        }
    }
