# tools/tool_request_tool.py

from shared.config import config
from shared.logger import logger
from modules.tools_safety import (
    get_safe_repo_root,
    resolve_safe_repo_path,
    mask_output,
)

import os
from datetime import datetime


def tool_request_tool(request: str) -> dict:
    """
    Documents a tool request by appending it to a file in the repository's
    'requests/' directory under the configured REPO_NAME.

    Args:
        request (str): The tool request description.

    Returns:
        dict: {
            "success": bool,
            "output": str
        }
    """
    try:
        # 1) Resolve the repository root safely
        repo_root = get_safe_repo_root()  # ensures REPO_NAME is set and valid

        # 2) Ensure a 'requests' subdirectory exists
        requests_dir = os.path.join(repo_root, "requests")
        os.makedirs(requests_dir, exist_ok=True)

        # 3) Build a timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"request_{timestamp}.txt"
        raw_path = os.path.join(requests_dir, filename)

        # 4) Canonicalize and guard the path
        safe_path = resolve_safe_repo_path(raw_path)

        # 5) Append the request
        with open(safe_path, "a", encoding="utf-8") as f:
            f.write(request.strip() + "\n")

        return {
            "success": True,
            "output": "Request documented successfully."
        }

    except Exception as e:
        # Log full exception
        logger.exception("Failed to document the tool request: %s", e)

        # Mask any absolute paths before returning
        err_msg = f"Failed to document the request: {e}"
        try:
            err_msg = mask_output(err_msg)
        except Exception:
            pass

        return {
            "success": False,
            "output": err_msg
        }

def get_tool():
    """
    Returns the tool spec for documenting tool requests.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_request_tool",
            "description": (
                "Documents a new tool request."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "Tool request description."
                    }
                },
                "required": ["request"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "one-time",
            "type": "readonly"
        }
    }
