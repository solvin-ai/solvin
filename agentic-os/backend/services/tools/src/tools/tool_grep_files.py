# tools/tool_grep_files.py

"""
Searches files for regex patterns using grep.
Input: an array of query objects [{ "pattern": <regex>, "file_path": <optional file path> }, ...].
If file_path is provided and points to a file, grep is run on that file and matching lines are returned.
If file_path is provided and points to a directory (or if not provided), a recursive search is performed
from that directory (or the repo root) and matching file paths are returned as a nested directory structure.
"""

import os
import subprocess

from shared.config import config
from shared.logger import logger

from modules.tools_safety import (
    get_repos_dir,
    get_log_dir,
    get_repo_path,
    resolve_repo_path,
    check_path,
    mask_output
)
from modules.tools_utils import group_paths


def tool_grep_files(queries: list):
    """
    Searches for regex patterns in files using grep.

    Input:
      queries (list): An array of query objects. Each object is a dict with:
        - "pattern" (string, required): Regex to search for.
        - "file_path" (string, optional): A file or directory path to search in.
          If omitted, the search starts at the repo root.

    Returns:
      dict: { "success": <bool>, "output": <list of { "query": ..., "result": ... }> }
    """
    if not queries or not isinstance(queries, list):
        return {"success": False, "output": "The queries parameter is required and must be a list of objects."}

    repo = config["REPO_NAME"]
    repo_root = get_repo_path(repo)

    overall_results = []

    for query in queries:
        if not isinstance(query, dict):
            overall_results.append({"query": query, "result": "Each query must be a dictionary."})
            continue

        pattern = query.get("pattern")
        if not pattern:
            overall_results.append({"query": query, "result": "The 'pattern' key is required in each query."})
            continue

        # Determine where to run grep: either the provided path or repo root
        candidate = query.get("file_path", ".")

        logger.debug(f"[tool_grep_files] Resolving candidate '{candidate}' with CWD: '{os.getcwd()}'")
        try:
            safe_path = resolve_repo_path(repo, candidate)
            safe_path = check_path(safe_path, allowed_root=repo_root)
        except Exception as e:
            overall_results.append({
                "query": query,
                "result": mask_output(f"Access denied or invalid path: {e}")
            })
            continue

        try:
            if os.path.isfile(safe_path):
                cmd = ["grep", "-nE", pattern, safe_path]
                completed = subprocess.run(cmd, capture_output=True, text=True)
                if completed.returncode not in (0, 1):
                    overall_results.append({
                        "query": query,
                        "result": mask_output(f"grep command failed with error: {completed.stderr.strip()}")
                    })
                    continue
                output = completed.stdout.strip()
                lines = output.splitlines() if output else []
                overall_results.append({"query": query, "result": lines})

            elif os.path.isdir(safe_path):
                cmd = ["grep", "-rlaE", pattern, "."]
                logger.debug(f"[tool_grep_files] Running recursive grep in directory='{safe_path}', cwd='{os.getcwd()}'")
                completed = subprocess.run(cmd, capture_output=True, text=True, cwd=safe_path)
                if completed.returncode not in (0, 1):
                    overall_results.append({
                        "query": query,
                        "result": mask_output(f"grep command failed with error: {completed.stderr.strip()}")
                    })
                    continue
                output = completed.stdout.strip()
                if output:
                    matches = output.splitlines()
                    nested = group_paths(matches)
                    overall_results.append({"query": query, "result": nested})
                else:
                    overall_results.append({"query": query, "result": []})

            else:
                overall_results.append({
                    "query": query,
                    "result": mask_output(f"Provided file_path is neither a file nor a directory: {safe_path}")
                })

        except Exception as e:
            overall_results.append({
                "query": query,
                "result": mask_output(f"Error: {e}")
            })

    return {"success": True, "output": overall_results}


def get_tool():
    """
    Returns the tool specification for grep files.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_grep_files",
            "description": (
                "Searches for regex patterns in files using grep. "
                "Accepts an array of query objects, each with a required 'pattern' and an optional 'file_path'. "
                "If no 'file_path' is provided, the search starts at the repository root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "description": (
                            "An array of query objects. Each object must have a 'pattern' (string) and may have "
                            "a 'file_path' (string, file or directory)."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "pattern": {
                                    "type": "string",
                                    "description": "Regex pattern to search for."
                                },
                                "file_path": {
                                    "type": "string",
                                    "description": "Optional file or directory path to search in."
                                }
                            },
                            "required": ["pattern"],
                            "additionalProperties": False,
                            "strict": True
                        }
                    }
                },
                "required": ["queries"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "readonly"
        }
    }
