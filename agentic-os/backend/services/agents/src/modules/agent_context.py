# modules/agent_context.py

import contextvars
from typing import Tuple, Optional

# define four context variables
_agent_role_var = contextvars.ContextVar("agent_role")
_agent_id_var   = contextvars.ContextVar("agent_id")
_repo_url_var   = contextvars.ContextVar("repo_url")


def set_current_agent(
    role:      str,
    agent_id:  str,
    repo:      str
) -> None:
    """
    Set the current agent context for:

      role, agent_id, repo_url

    so that downstream helpers (get_turns_list, add_turn_to_list, etc.)
    can default to these values if not passed explicitly.
    """
    _agent_role_var.set(role)
    _agent_id_var.set(agent_id)
    _repo_url_var.set(repo)


def get_current_agent() -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[str]
]:
    """
    Return the current agent context as a 4‐tuple:
      (agent_role, agent_id, repo_url)
    Any of these may be None if not set.
    """
    return (
        _agent_role_var.get(None),
        _agent_id_var.get(None),
        _repo_url_var.get(None),
    )
