# modules/ask_agent.py

"""
Top‐level agent “ask” entrypoint.
Dispatches either to a simple echo‐only reply or to the full LLM orchestrator.
"""

import json
from datetime import datetime

from shared.client_agents import list_registry, list_messages
from modules.messages_llm import get_assistant_response

def is_echo_agent(agent_role: str) -> bool:
    """
    Returns True if the given agent_role’s allowed_tools is exactly ["echo"].
    """
    data = list_registry()
    rows = data.get("agentTypes", data) if isinstance(data, dict) else data
    for row in rows:
        if row.get("agent_role") == agent_role:
            raw_tools = row.get("allowed_tools", [])
            if isinstance(raw_tools, str):
                try:
                    parsed = json.loads(raw_tools)
                    raw_tools = parsed if isinstance(parsed, list) else []
                except Exception:
                    raw_tools = []
            if isinstance(raw_tools, list) and set(raw_tools) == {"echo"}:
                return True
    return False

def ask_agent(agent_role: str, agent_id: str) -> dict:
    """
    If this role is echo‐only, repeat the last user message.
    Otherwise delegate to the LLM‐only ask_agent implementation.
    """
    if is_echo_agent(agent_role):
        msgs = list_messages(agent_role, agent_id)
        content = ""
        orig_id = None
        # find the most recent user message
        for m in reversed(msgs):
            if m.get("role") == "user":
                content = m.get("content", "")
                orig_id = m.get("message_id")
                break
        return {
            "content": content,
            "meta": {
                "timestamp": datetime.utcnow().isoformat(),
                "char_count": len(content),
                "original_message_id": orig_id,
            }
        }
    else:
        return get_assistant_response(agent_role, agent_id)
