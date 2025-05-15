# tools/tool_run_bash.py

"""
Executes a bash command inside the configured repository sandbox
and returns its output.
"""

import subprocess

from shared.logger import logger
from modules.tools_safety import get_safe_repo_root, mask_output


def tool_run_bash(bash_command: str) -> dict:
    """
    Executes the given bash command in the repo defined by REPO_NAME,
    and returns a dict with:
      - success (bool)
      - output  (str): masked stdout or stderr
    """
    # Fetch and validate the repo root (checks REPO_NAME, existence, sandboxing)
    try:
        safe_cwd = get_safe_repo_root()
    except RuntimeError as e:
        return {"success": False, "output": str(e)}

    # Run the command
    proc = subprocess.run(
        ["bash", "-c", bash_command],
        cwd=safe_cwd,
        capture_output=True,
        text=True,
    )

    # On error, mask stderr
    if proc.returncode != 0:
        return {
            "success": False,
            "output": f"Error: {mask_output(proc.stderr.strip())}"
        }

    # On success, mask stdout or give fallback message
    out = proc.stdout.strip()
    if out:
        return {"success": True, "output": mask_output(out)}
    return {"success": True, "output": "Command executed without output."}


def get_tool():
    """
    Returns the tool specification for running bash commands.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_run_bash",
            "description": (
                "Executes a bash command inside the configured repo sandbox "
                "and returns { success, output }."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bash_command": {
                        "type": "string",
                        "description": "The bash command to execute."
                    }
                },
                "required": ["bash_command"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "mutating"
        }
    }
