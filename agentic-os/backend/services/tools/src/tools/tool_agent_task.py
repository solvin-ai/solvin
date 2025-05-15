# tools/tool_agent_task.py

from typing import Optional, Dict, Any

from modules.tools_safety import get_repos_dir, get_repo_path, check_path, mask_output
from shared.client_agents import run_agent_task
from shared.config import config

def tool_agent_task(
    agent_role:       str,
    task_user_prompt: str,
    agent_id:         Optional[str] = None,
) -> Dict[str, Any]:
    """
    RPC‐style helper that:
      1) Enforces sandbox safety on the repo path (from config)
      2) Delegates find‐or‐create + send‐message + run‐to‐completion
         to the Agents‐service via our run_agent_task wrapper
      3) Unwraps the result and masks any absolute paths

    Returns:
      {
        "success":     bool,
        "task_result": <the run_agent_task data or error string>,
        "agent_id":    <string|null>
      }
    """
    # 1) Determine repository from config and enforce sandbox safety
    repo = config.get("REPO_NAME", "")
    repo_root = get_repo_path(repo)
    repo_root = check_path(repo_root, allowed_root=get_repos_dir())

    repo_url = config.get("REPO_URL")

    try:
        # 2) Delegate the full workflow to run_agent_task
        resp = run_agent_task(
            agent_role       = agent_role,
            repo_url         = repo_url,
            user_prompt      = task_user_prompt,
            agent_id         = agent_id,
        )
    except Exception as e:
        return {
            "success":     False,
            "task_result": mask_output(f"exception: {e}"),
            "agent_id":    None
        }

    # 3) Unwrap and mask any absolute paths in a string
    success = resp.get("success", False)
    result  = resp.get("task_result")
    if isinstance(result, str):
        result = mask_output(result)

    return {
        "success":     success,
        "task_result": result,
        "agent_id":    resp.get("agent_id")
    }


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_agent_task",
            "description": (
                "Send a task user prompt to an agent, drive it to completion, and return the result"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_role": {
                        "type": "string",
                        "description": "Which agent role to call"
                    },
                    "task_user_prompt": {
                        "type": "string",
                        "description": "The task to hand off to the agent"
                    },
                    "agent_id": {
                        "type": ["string", "null"],
                        "description": "Optional existing agent_id to continue with existing agent context"
                    }
                },
                "required": ["agent_role", "task_user_prompt"],
                "additionalProperties": False
            }
        },
        "internal": {
            "preservation_policy": "until_build",
            "type": "mutating"
        }
    }
