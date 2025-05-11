# tools/tool_agents_broadcast.py

from shared.config import config
from modules.tools_safety import get_repos_dir, get_repo_path, check_path, mask_output
from typing import Optional
from shared.client_agents import broadcast_to_agents


def tool_agents_broadcast(
    agent_roles: list,
    message: str,
    repo_name: Optional[str] = None
) -> dict:
    """
    Broadcasts a message to all live agents of the specified roles
    via the RPC‐style /messages/broadcast endpoint.

    Parameters:
      agent_roles: list of agent_role strings
      message:     the text to broadcast
      repo_name:   optional override (defaults to config.REPO_NAME)

    Returns:
      { success: bool, details: str, errors?: [str] }
    """
    # sandbox safety: ensure the repo root is valid and canonical
    repo = repo_name or config.get("REPO_NAME", "")
    repo_root = get_repo_path(repo)
    # this will realpath() and assert it lives under get_repos_dir()
    check_path(repo_root, allowed_root=get_repos_dir())

    try:
        # broadcast_to_agents returns the full FastAPI envelope:
        # { data: { success_count, errors? }, meta:…, errors:[…] }
        resp = broadcast_to_agents(agent_roles, message, repo_name=repo)

        # First, any top‐level transport errors?
        top_errors = resp.get("errors") or []
        if top_errors:
            msgs = [e.get("message", str(e)) for e in top_errors]
            details = "Broadcast RPC returned errors: " + "; ".join(msgs)
            return {
                "success": False,
                "details": mask_output(details)
            }

        data = resp.get("data") or {}
        success_count = data.get("success_count", 0)
        agent_errors  = data.get("errors") or []

        if success_count <= 0:
            details = (
                "Broadcast failed; no agents received the message."
                + (" Errors: " + "; ".join(agent_errors) if agent_errors else "")
            )
            return {
                "success": False,
                "details": mask_output(details),
                "errors": agent_errors,
            }

        # Success path
        details = (
            f"Broadcast message sent to {success_count} agents."
            + (" Errors: " + "; ".join(agent_errors) if agent_errors else "")
        )
        return {
            "success": True,
            "details": mask_output(details),
            "errors": agent_errors,
        }

    except Exception as e:
        details = f"Exception while broadcasting: {e}"
        return {
            "success": False,
            "details": mask_output(details)
        }


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_agents_broadcast",
            "description": (
                "Broadcasts a message to all live agents of the specified roles "
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Which agent_role groups to broadcast to"
                    },
                    "message": {
                        "type": "string",
                        "description": "The message to send"
                    },
                    "repo_name": {
                        "type": "string",
                        "description": "Optional repo_name override"
                    }
                },
                "required": ["agent_roles", "message"],
                "additionalProperties": False
            }
        },
        "internal": {
            "preservation_policy": "one-of",
            "type": "readonly"
        }
    }
