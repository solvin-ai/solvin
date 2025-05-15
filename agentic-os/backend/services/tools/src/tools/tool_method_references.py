# tools/tool_method_references.py

import json
import subprocess
import os
from collections import defaultdict

from shared.logger import logger
from shared.config import config

from modules.tools_safety import (
    get_repo_path,
    resolve_repo_path,
    check_path,
    mask_output,
)


def tool_method_references(method_name: str, language: str = None) -> dict:
    """
    Searches for all invocations of the specified method using semgrep.

    Args:
        method_name (str): Name of the method to search for.
        language (str, optional): semgrep language to restrict the search to
            (e.g. "java" or "python"). If None, semgrep will auto-detect.

    Returns:
        dict: A dictionary with the keys:
              • "success": A boolean indicating if the operation completed without errors.
              • "output": If successful, a formatted string listing file and line references;
                          otherwise an error message.
    """
    try:
        # Sandbox safety
        repo = config.get("REPO_NAME")
        if not repo:
            raise Exception("Required configuration key 'REPO_NAME' is not set!")
        repo_root = get_repo_path(repo)

        # Resolve and lock down the path to the repo root
        repo_path = resolve_repo_path(repo, ".")
        repo_path = check_path(repo_path, allowed_root=repo_root)

        logger.debug(f"[tool_method_references] Repository path: {repo_path}, cwd: {os.getcwd()}")

        target_directory = repo_path
        pattern = f"{method_name}(...)"

        # Build semgrep command
        cmd = ["semgrep", "--json", "--pattern", pattern]
        if language:
            cmd += ["--lang", language]
        cmd.append(target_directory)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as fnf_error:
            raise Exception("semgrep not found. Please install it and ensure it's in PATH.") from fnf_error

        if result.returncode != 0:
            return {
                "success": False,
                "output": mask_output(f"Error executing semgrep: {result.stderr.strip()}")
            }

        data = json.loads(result.stdout)
        if not data.get("results"):
            return {
                "success": True,
                "output": mask_output(f"No references found for method '{method_name}'.")
            }

        # Aggregate by file
        results_by_file = defaultdict(list)
        for res in data["results"]:
            file_path = res.get("path", "Unknown file")
            line_num = res.get("start", {}).get("line", "Unknown line")
            snippet = res.get("extra", {}).get("lines", "").strip() or f"Line {line_num}"
            results_by_file[file_path].append(f"Line {line_num}: {snippet}")

        # Format output
        formatted_lines = []
        for file_path, usages in results_by_file.items():
            formatted_lines.append(f"File: {file_path}")
            for usage in usages:
                formatted_lines.append("  " + usage)
            formatted_lines.append("")  # blank line between files

        final_output = "\n".join(formatted_lines)
        return {"success": True, "output": mask_output(final_output)}

    except Exception as e:
        logger.exception("Error in tool_method_references: %s", e)
        return {"success": False, "output": mask_output(str(e))}


def get_tool():
    """
    Returns the tool specification for method references.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_method_references",
            "description": (
                "Finds method invocations across all files in the repository using semgrep. "
                "You can optionally restrict to a single language (e.g. 'java' or 'python'), "
                "or leave unset for auto-detect."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method_name": {
                        "type": "string",
                        "description": "Name of the method to search for."
                    },
                    "language": {
                        "type": "string",
                        "description": "Optional semgrep language filter, e.g. 'java' or 'python'."
                    }
                },
                "required": ["method_name"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "readonly"
        }
    }
