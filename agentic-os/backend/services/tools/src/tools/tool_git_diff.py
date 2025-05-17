# tools/tool_git_diff.py

"""
Executes 'git diff HEAD' for a list of file paths and returns a dictionary mapping
each file path to its diff output. The function verifies that each file is inside the
repository and tracked by git. Files not tracked or outside the repository are rejected.
"""

import os
import subprocess

from shared.config import config
from shared.logger import logger
from modules.tools_safety import resolve_repo_path, check_path, mask_output


def tool_git_diff(file_paths: list) -> dict:
    """
    Args:
        file_paths (list of str): Relative or absolute paths to diff, at least one must be provided.
    Returns:
        dict: { "success": bool, "output": { "<file>": "<diff or error>" } }
    """
    repo_name = config.get("REPO_NAME")
    if not repo_name:
        err = "REPO_NAME must be set in config."
        logger.error(f"[tool_git_diff] {err}")
        return {"success": False, "output": mask_output(err)}

    # Resolve repo root ('.') under the named repo
    try:
        repo_root = resolve_repo_path(repo_name, ".")
    except Exception as e:
        err = f"Error resolving repository root for '{repo_name}': {e}"
        logger.error(f"[tool_git_diff] {err}")
        return {"success": False, "output": mask_output(err)}

    if not file_paths:
        err = "At least one file must be provided for diff."
        logger.error(f"[tool_git_diff] {err}")
        return {"success": False, "output": mask_output(err)}

    diff_results = {}
    overall_success = True

    for path in file_paths:
        try:
            # Resolve & sandbox the file path under repo_root
            safe_path = resolve_repo_path(repo_name, path)
            safe_path = check_path(safe_path, allowed_root=repo_root)
            logger.debug(
                f"[tool_git_diff] Resolved '{path}' → '{safe_path}'"
            )
        except Exception as e:
            key = mask_output(path)
            diff_results[key] = f"Access denied or invalid path: {e}"
            overall_success = False
            continue

        # Compute git‐relative path
        rel_path = os.path.relpath(safe_path, repo_root)
        key = mask_output(rel_path)

        # Is it tracked?
        proc_ls = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel_path],
            cwd=repo_root,
            capture_output=True, text=True
        )
        if proc_ls.returncode != 0:
            diff_results[key] = "File is not tracked in the git repository. Diff rejected."
            overall_success = False
            continue

        # Run git diff, ignore volatile date lines
        proc_diff = subprocess.run(
            [
                "git", "-C", repo_root, "diff",
                "-I", r'date = "[^"]*"', "HEAD", "--", rel_path
            ],
            capture_output=True, text=True
        )
        if proc_diff.returncode != 0:
            err = proc_diff.stderr.strip() or "<no stderr>"
            diff_results[key] = "git diff failed: " + mask_output(err)
            overall_success = False
        else:
            out = proc_diff.stdout.strip()
            diff_results[key] = mask_output(out) if out else "No differences found."

    return {"success": overall_success, "output": diff_results}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_git_diff",
            "description": (
                "Returns git diff output for the specified list of file paths. "
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "description": "List of file paths to diff. At least one file must be provided.",
                        "items": {"type": "string"},
                    },
                },
                "required": ["file_paths"],
                "additionalProperties": False,
                "strict": True,
            },
        },
        "internal": {
            "preservation_policy": "until-update",
            "type": "readonly",
        },
    }
