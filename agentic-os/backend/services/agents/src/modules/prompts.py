# modules/prompts.py

"""
Generic prompt‐builder for agents that sets up initial messages.
Fetches system and developer prompts from the agent registry via a local module.
By default it will fall back to the contextvars‐based current agent, but you can
pass (agent_role, agent_id, repo_url) explicitly if you call it outside of
run_to_completion or turns_list.

The system message always contains the required token "json" so that downstream
LLM APIs accept it.

This function must only be called on an empty history; it will throw
if history already contains any turns.
"""

from typing import List, Any, Optional
from shared.config import config
from shared.logger import logger
from modules.agents_temp_registry import get_agent_role
from modules.unified_turn import UnifiedTurn


def initialize_initial_turn_history(
    history:      List[Any],
    agent_role:   Optional[str] = None,
    agent_id:     Optional[str] = None,
    repo_url:     Optional[str] = None,
    initial_user: str            = ""
) -> List[Any]:
    """
    Create turn‐0 exactly once, containing:
      • system prompt (must mention “json”)
      • developer prompt (from agent registry)
      • optional initial user prompt

    Parameters:
      history:      list to append the new turn to (must be empty)
      agent_role:   override current agent’s role
      agent_id:     override current agent’s ID
      repo_url:     override current agent’s repo_url
      initial_user: optional initial user content

    Raises:
      RuntimeError if history is non‐empty when called.
    """
    # 0) guard: only call on brand‐new history
    if history:
        raise RuntimeError(
            "initialize_initial_turn_history() called on non-empty history; "
            "turn-0 must only be created once."
        )

    # 1) resolve context‐vars if not provided (lazy import to avoid circular)
    if not (agent_role and agent_id and repo_url):
        from modules.agents_running import get_current_agent_tuple as get_current_agent
        agent_role, agent_id, repo_url = get_current_agent()
    if not agent_role:
        raise RuntimeError(
            "initialize_initial_turn_history: no agent_role provided or in context"
        )

    # 2) system prompt (must contain “json”)
    sys_cfg = config.get("LLM_SYSTEM_PROMPT", "")
    default_system = "Always respond with a valid json object."
    if sys_cfg and "json" in sys_cfg.lower():
        system_content = sys_cfg
    else:
        system_content = default_system

    # 3) developer prompt (from registry)
    entry = get_agent_role(agent_role) or {}
    developer_content = entry.get("default_developer_prompt", "")

    # 4) assemble turn-0 metadata + messages
    turn_meta = {
        "turn":      0,
        "finalized": True,
        "tool_meta": {},
    }
    raw_messages = {
        "system":    {"raw": {"role": "system",    "content": system_content}},
        "developer": {"raw": {"role": "developer", "content": developer_content}},
    }
    if initial_user:
        raw_messages["user"] = {"raw": {"role": "user", "content": initial_user}}

    # 5) create and append turn-0
    ut0 = UnifiedTurn.create_turn(turn_meta, raw_messages)
    history.append(ut0)

    # 6) log out what we’ve seeded
    logger.info("Initialized turn-0")
    logger.info("  system:    %r", system_content)
    logger.info("  developer: %r", developer_content)
    if initial_user:
        logger.info("  user:      %r", initial_user)

    return history
