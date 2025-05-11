# modules/agent_context.py

import contextvars
from typing import Tuple, Optional

# define three context variables
_agent_role_var = contextvars.ContextVar("agent_role")
_agent_id_var   = contextvars.ContextVar("agent_id")
_repo_url_var  = contextvars.ContextVar("repo_url")

def set_current_agent(role: str, agent_id: str, repo: str) -> None:
    _agent_role_var.set(role)
    _agent_id_var.set(agent_id)
    _repo_url_var.set(repo)

def get_current_agent() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    return (
        _agent_role_var.get(None),
        _agent_id_var.get(None),
        _repo_url_var.get(None),
    )
