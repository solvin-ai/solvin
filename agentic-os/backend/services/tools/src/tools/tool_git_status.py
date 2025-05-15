# tools/tool_git_status.py

from shared.config import config
from modules.tools_safety import get_repos_dir, get_log_dir, get_repo_path, resolve_repo_path, check_path, mask_output
import subprocess
import os
import json

from shared.logger import logger

from modules.tools_utils import group_paths

def parse_git_status(status):
    """
    Parse the porcelain output from git status and return a JSON string with structured file lists.

    It extracts:
      - Modified files (tracked changes) from lines whose two-character status is not "??".
      - Untracked files (added) from lines starting with "??".

    For untracked files, it filters out filenames ending with .last or .bak.

    The returned JSON has the format:
      {"modified": [...], "added": [...]}
    """
    modified_files = []
    added_files = []
    lines = status.splitlines()
    for line in lines:
        if not line.strip() or len(line) < 4:
            continue
        code = line[:2]
        filepath = line[3:].strip()
        if code == "??":
            if filepath.endswith(".last") or filepath.endswith(".bak"):
                continue
            added_files.append(filepath)
        else:
            modified_files.append(filepath)
    grouped_modified = group_paths(modified_files)
    grouped_added = group_paths(added_files)
    result = {"modified": grouped_modified, "added": grouped_added}
    return json.dumps(result)

def tool_git_status() -> dict:
    """
    Executes 'git status --porcelain' and returns the repository status.

    Returns:
        dict: A dictionary containing:
              - "success": A boolean indicating whether the command succeeded.
              - "output": A JSON object with structured git status details.
                        The JSON object has the format {"modified": [...], "added": [...]}
    """
    try:
        # sandbox safety via tools_safety helpers
        repo = config["REPO_NAME"]
        repo_root = get_repo_path(repo)
        repo_path = resolve_repo_path(repo, ".")

        # Log the repository path before executing git status.
        logger.debug("[tool_git_status] Using repo_path='%s'", repo_path)

        proc = subprocess.run(
            "git status --porcelain",
            shell=True,
            capture_output=True,
            text=True,
            cwd=repo_path
        )
        if proc.returncode != 0:
            error_message = f"git status failed: {proc.stderr.strip()}"
            logger.error(error_message)
            return {"success": False, "output": error_message}

        output = proc.stdout.strip()
        if not output:
            return {"success": True, "output": {"modified": [], "added": []}}

        parsed_json_str = parse_git_status(output)
        parsed_json = json.loads(parsed_json_str)
        return {"success": True, "output": parsed_json}

    except Exception as e:
        logger.exception("Exception in tool_git_status: %s", e)
        return {"success": False, "output": str(e)}

def get_tool():
    """
    Returns the tool specification for git status.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_git_status",
            "description": "Returns the current git status as a structured JSON with compressed file grouping, using '--porcelain' output.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "one-of",
            "type": "readonly"
        }
    }

