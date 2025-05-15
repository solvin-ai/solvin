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
    # Ensure we know which repo to operate on
    repo_name = config.get("REPO_NAME")
    if not repo_name:
        raise RuntimeError("REPO_NAME must be set in config.")
    # This both constructs and validates the repo root
    repo_root = resolve_repo_path(repo_name, ".")

    try:
        if not file_paths:
            raise ValueError("At least one file must be provided for diff.")

        diff_results = {}
        overall_success = True

        for file_path in file_paths:
            # Normalize to absolute before checking
            candidate = os.path.abspath(file_path)
            logger.debug(
                f"[tool_git_diff] Before check_path for file_path='{file_path}'. "
                f"Candidate='{candidate}', cwd='{os.getcwd()}'"
            )

            # This will realpath() and assert the path is under repo_root
            safe_file_path = check_path(candidate, allowed_root=repo_root)
            logger.debug(
                f"[tool_git_diff] After check_path for file_path='{file_path}'. "
                f"safe_file_path='{safe_file_path}', cwd='{os.getcwd()}'"
            )

            # Reject anything outside the repo
            if not safe_file_path.startswith(repo_root + os.sep) and safe_file_path != repo_root:
                safe_key = mask_output(safe_file_path)
                diff_results[safe_key] = "File is not within the current repository."
                overall_success = False
                continue

            # Compute git‐relative path and scrub it for keys
            relative_path = os.path.relpath(safe_file_path, repo_root)
            safe_key = mask_output(relative_path)

            # Check that it's tracked by git
            cmd_ls = ["git", "ls-files", "--error-unmatch", relative_path]
            proc_ls = subprocess.run(cmd_ls, capture_output=True, text=True, cwd=repo_root)
            if proc_ls.returncode != 0:
                diff_results[safe_key] = "File is not tracked in the git repository. Diff rejected."
                overall_success = False
                continue

            # Finally, run git diff, ignoring volatile date lines
            cmd_diff = [
                "git",
                "-C",
                repo_root,
                "diff",
                "-I",
                r'date = "[^"]*"',
                "HEAD",
                "--",
                relative_path,
            ]
            proc_diff = subprocess.run(cmd_diff, capture_output=True, text=True)
            if proc_diff.returncode != 0:
                err = proc_diff.stderr.strip() or "<no stderr>"
                diff_results[safe_key] = "git diff failed: " + mask_output(err)
                overall_success = False
            else:
                out = proc_diff.stdout.strip()
                diff_results[safe_key] = mask_output(out) if out else "No differences found."

        return {"success": overall_success, "output": diff_results}

    except Exception as e:
        logger.error(f"[tool_git_diff] Error: {e}")
        return {"success": False, "output": mask_output(str(e))}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_git_diff",
            "description": (
                "Returns git diff output for the specified list of file paths. "
                "Each provided file is checked to verify that it resides within the current repository. "
                "Files not tracked are rejected."
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
