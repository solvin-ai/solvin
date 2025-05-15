# tools/tool_git_restore.py

from shared.config import config
from modules.tools_safety import (
    get_repos_dir,
    get_log_dir,
    get_repo_path,
    resolve_repo_path,
    check_path,
    mask_output,
)

"""
A tool to restore specified files using git restore.
"""

import subprocess
import os
from shared.logger import logger

logger = logger

def tool_git_restore(file_paths: list) -> dict:
    # Ensure we’re operating inside the configured repository
    repo = config["REPO_NAME"]
    repo_root = resolve_repo_path(repo, ".")  # includes its own safety checks

    try:
        if not isinstance(file_paths, list):
            error = "file_paths must be an array of file path strings."
            logger.error(error)
            return {"success": False, "output": error}

        if not file_paths:
            error = "No file paths provided for restoration."
            logger.error(error)
            return {"success": False, "output": error}

        adjusted_file_paths = []
        for path in file_paths:
            logger.debug(
                f"[tool_git_restore] Resolving candidate '{path}' with CWD: '{os.getcwd()}'"
            )
            safe_abs_path = resolve_repo_path(repo, path)
            logger.debug(
                f"[tool_git_restore] Resolved file path: '{safe_abs_path}', cwd: '{os.getcwd()}'"
            )
            relative_path = os.path.relpath(safe_abs_path, repo_root)
            adjusted_file_paths.append(relative_path)

        command = ["git", "restore"] + adjusted_file_paths
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=repo_root
        )
        if proc.returncode != 0:
            error_message = mask_output(proc.stderr.strip())
            logger.error(error_message)
            return {"success": False, "output": error_message}

        return {"success": True, "output": "Files restored successfully."}

    except Exception as e:
        logger.error(f"[tool_git_restore] Error: {str(e)}")
        return {"success": False, "output": mask_output(str(e))}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_git_restore",
            "description": "Restores the specified files using git restore.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file relative paths to restore."
                    }
                },
                "required": ["file_paths"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "mutating"
        }
    }
