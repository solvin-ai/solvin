# tools/tool_agent_task.py

from shared.config import config
from modules.tools_safety import get_repos_dir, get_repo_path, check_path, mask_output

from typing import Optional

from shared.client_agents import (
    add_running_agent,
    add_message,
    run_to_completion,
)

def tool_agent_task(
    agent_role: str,
    task_user_prompt: str,
    repo_name: Optional[str] = None
) -> dict:
    """
    RPC-style helper that:
      1. Creates a new running agent
      2. Sends it a 'user' message with the task prompt
      3. Invokes run_to_completion
      4. Unwraps each RPC envelope and reports any errors

    Returns:
      {
        "success": bool,
        "task_result": <the run_to_completion data or error string>,
        "agent_id":   <string|null>
      }
    """
    # Determine repository and enforce sandbox safety
    repo = repo_name or config.get("REPO_NAME", "")
    # Build the repo path and ensure it lives under REPOS_DIR
    repo_root = get_repo_path(repo)
    # This will raise RuntimeError if repo_root is outside of get_repos_dir()
    repo_root = check_path(repo_root, allowed_root=get_repos_dir())

    try:
        # 1) create the agent
        rec = add_running_agent(agent_role, repo_name=repo)
        if rec.get("errors"):
            raw_msg = "; ".join(err.get("message", "") for err in rec["errors"])
            err_msg = mask_output(raw_msg)
            return {
                "success": False,
                "task_result": f"agent creation error: {err_msg}",
                "agent_id": None
            }

        agent_id = rec.get("data", {}).get("agent_id") or rec.get("data", {}).get("id")
        if not agent_id:
            return {
                "success": False,
                "task_result": mask_output("agent creation failed (no agent_id returned)"),
                "agent_id": None
            }

        # 2) add the user prompt as the first message
        msg_resp = add_message(
            agent_role=agent_role,
            agent_id=agent_id,
            role="user",
            content=task_user_prompt,
            repo_name=repo
        )
        if msg_resp.get("errors"):
            raw_msg = "; ".join(err.get("message", "") for err in msg_resp["errors"])
            err_msg = mask_output(raw_msg)
            return {
                "success": False,
                "task_result": mask_output(f"add_message error: {err_msg}"),
                "agent_id": agent_id
            }

        # 3) run to completion
        run_resp = run_to_completion(
            agent_role=agent_role,
            user_prompt=task_user_prompt,
            agent_id=agent_id,
            repo_name=repo
        )
        if run_resp.get("errors"):
            raw_msg = "; ".join(err.get("message", "") for err in run_resp["errors"])
            err_msg = mask_output(raw_msg)
            return {
                "success": False,
                "task_result": mask_output(f"run_to_completion error: {err_msg}"),
                "agent_id": agent_id
            }

        # 4) success: unwrap data, masking any absolute paths if it's a string
        result = run_resp.get("data")
        if isinstance(result, str):
            result = mask_output(result)

        return {
            "success": True,
            "task_result": result,
            "agent_id": agent_id
        }

    except Exception as e:
        # Catch any sandbox or other unexpected errors
        return {
            "success": False,
            "task_result": mask_output(f"exception: {e}"),
            "agent_id": None
        }


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_agent_task",
            "description": (
                "Creates a new running agent of the given role, sends it the user task prompt"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_role": {
                        "type": "string",
                        "description": "Which agent_role to instantiate"
                    },
                    "task_user_prompt": {
                        "type": "string",
                        "description": "The user prompt (task) to hand off"
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
