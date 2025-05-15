# tools/tool_last_change_diff.py

from shared.config import config
from shared.logger import logger

from modules.tools_safety import (
    get_safe_repo_root,
    resolve_safe_repo_path,
    mask_output,
)

import subprocess
import os

"""
Returns the diff of the last change for each specified file by comparing
the current file with its ".last" version.
"""


def tool_last_change_diff(file_paths: list) -> dict:
    """
    For each file in file_paths, checks if a corresponding file named "<file_path>.last" exists.
    If the backup file exists, this function runs the diff command:
         diff --report-identical-files --text <file_path>.last <file_path>
    If the diff command finds no differences, an appropriate message is returned.
    If either the current file or the backup file does not exist or an error occurs,
    an error message is included in the output.

    Args:
        file_paths (list): List of file paths to diff.

    Returns:
        dict: A dictionary with keys:
              - "success": Boolean indicating overall success.
              - "output": A dictionary mapping each resolved file_path to its diff text or error message.
    """
    if not file_paths:
        return {"success": False, "output": "At least one file_path must be provided."}

    # Determine and validate the repository root from REPO_NAME in config
    # This ensures all paths stay inside that repo, whether in-container or host.
    repo_root = get_safe_repo_root()

    overall_success = True
    diff_results = {}

    for file_path in file_paths:
        # Resolve and validate the target file path under the repo root
        try:
            safe_file_path = resolve_safe_repo_path(file_path)
        except RuntimeError as e:
            diff_results[file_path] = f"Invalid path: {e}"
            overall_success = False
            continue

        backup_file = safe_file_path + ".last"
        if not os.path.exists(backup_file):
            diff_results[safe_file_path] = f"Backup file '{backup_file}' does not exist."
            overall_success = False
            continue

        cmd = ["diff", "--report-identical-files", "--text", backup_file, safe_file_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode not in (0, 1):
            # unexpected error
            diff_results[safe_file_path] = mask_output(f"Error running diff: {proc.stderr.strip()}")
            overall_success = False
        elif proc.returncode == 0:
            # files are identical
            diff_results[safe_file_path] = "No differences detected."
        else:
            # diff output
            diff_results[safe_file_path] = proc.stdout.strip()

    return {"success": overall_success, "output": diff_results}


def get_tool():
    """
    Returns the tool specification for tool_last_change_diff.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_last_change_diff",
            "description": (
                "Returns the diff of the most recent change for each file provided, comparing "
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "description": "List of relative file paths (to the repo).",
                        "items": {"type": "string"}
                    }
                },
                "required": ["file_paths"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-update",
            "type": "readonly"
        }
    }
