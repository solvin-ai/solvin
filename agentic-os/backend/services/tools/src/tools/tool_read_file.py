# tools/tool_read_file.py

"""
Reads contents of a file.
"""

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

import os
import json

ENCODING = "utf-8"

def tool_read_file(file_path: str) -> dict:
    """
    Reads and returns the content of the specified file.

    Args:
        file_path (str): A relative path (to the repository root) or absolute path to the file.

    Returns:
        dict: A dictionary with "success" (bool) and "output" containing the file content
              or an error message.
    """
    repo = config.get("REPO_NAME")
    if not repo:
        err = "REPO_NAME is not set in config."
        logger.error(f"[tool_read_file] {err}")
        return {"success": False, "output": mask_output(err)}

    repo_root = get_repo_path(repo)

    logger.debug(
        f"[tool_read_file] Received file_path: '{file_path}', "
        f"cwd: '{os.getcwd()}', repo_root: '{repo_root}'"
    )

    try:
        # Resolve and sandbox the target path
        safe_file_path = resolve_repo_path(repo, file_path)
        # Double-check that it's under the repo root
        safe_file_path = check_path(safe_file_path, allowed_root=repo_root)
        logger.debug(f"[tool_read_file] Resolved safe_file_path: '{safe_file_path}'")
    except Exception as e:
        error_msg = f"Error resolving file path '{file_path}': {e}"
        logger.error(f"[tool_read_file] {error_msg}, cwd: '{os.getcwd()}'")
        return {"success": False, "output": mask_output(error_msg)}

    if not os.path.exists(safe_file_path):
        output = json.dumps({
            "status": "not_found",
            "message": f"The file '{mask_output(safe_file_path)}' does not exist."
        })
    else:
        try:
            with open(safe_file_path, "r", encoding=ENCODING) as f:
                content = f.read()
            output = mask_output(content)
        except UnicodeDecodeError as ude:
            output = json.dumps({
                "status": "error",
                "message": (
                    f"Cannot decode file '{mask_output(safe_file_path)}' "
                    f"with encoding '{ENCODING}': {ude}"
                )
            })
        except Exception as e:
            output = json.dumps({
                "status": "error",
                "message": (
                    f"An error occurred while reading "
                    f"'{mask_output(safe_file_path)}': {e}"
                )
            })

    return {"success": True, "output": output}


def get_tool():
    """
    Returns the tool specification for reading a file.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_read_file",
            "description": "Reads file content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "A relative path (from the repository root) to the file."
                    }
                },
                "required": ["file_path"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-update",
            "type": "readonly"
        }
    }
