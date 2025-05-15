# modules/turns_summarization.py

"""
Summarization and pruning of chat turns via LLM.

This module:
  1) Grabs the current in‐memory turn history.
  2) If the number of body turns (beyond the initial system+developer turn) exceeds
     `max_body_turns`, it:
       a) Extracts the oldest body turns to be pruned.
       b) Builds a summary prompt from only their assistant/tool messages.
       c) Calls the LLM (via modules/llm_client.call_llm).
       d) Inserts that summary as a new “user” turn immediately after the initial turn.
       e) Drops the pruned turns and keeps only the last `max_body_turns` body turns.
       f) Reindexes all turns sequentially (0…N−1).
       g) Persists the updated history via save_turns_list.
"""

import os
import json
import logging
from typing import List, Optional

from modules.turns_list import get_turns_list, save_turns_list
from modules.llm_client import call_llm
from modules.unified_turn import UnifiedTurn

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

DEFAULT_MODEL = os.getenv("SUMMARY_MODEL", "gpt-4")
DEFAULT_TEMPERATURE = float(os.getenv("SUMMARY_TEMPERATURE", "0.0"))


def summarize_and_purge_turns(
    agent_role:    str,
    agent_id:      str,
    repo_url:      str,
    max_body_turns: int                = 10,
    summary_role:   str                = "developer",
    model:          Optional[str]      = None,
    temperature:    Optional[float]    = None,
) -> None:
    """
    Perform summarization and pruning of old turns, if needed.

    - agent_role, agent_id, repo_url: identify the conversation.
    - max_body_turns: how many recent body turns to keep.
    - summary_role: role to assign to the summarization prompt.
    - model, temperature: override defaults if provided.
    """
    history: List[UnifiedTurn] = get_turns_list(
        agent_role, agent_id, repo_url
    )
    total = len(history)
    logger.debug(
        "summarize_and_purge: %d total turns for %s/%s@%s [%s]",
        total, agent_role, agent_id, repo_url
    )

    # Nothing to do if within limit (initial turn + max_body_turns)
    if total <= 1 + max_body_turns:
        logger.debug(
            "No summarization needed (total %d ≤ initial+%d)",
            total, max_body_turns
        )
        return

    # Split out the initial system+developer turn and the rest
    initial_turn = history[0]
    body_turns   = history[1:]
    prune_count  = len(body_turns) - max_body_turns
    pruned       = body_turns[:prune_count]
    kept         = body_turns[prune_count:]

    # Build and call the summarization LLM
    prompt       = _build_summary_prompt(pruned)
    messages     = [
        {"role": "system",    "content": "You are a chat history summarization assistant."},
        {"role": summary_role, "content": prompt},
    ]
    model_to_use = model or DEFAULT_MODEL
    temp_to_use  = temperature if temperature is not None else DEFAULT_TEMPERATURE

    try:
        raw = call_llm(
            model=model_to_use,
            messages=messages,
            temperature=temp_to_use
        )
    except Exception as e:
        logger.error("LLM summarization failed: %s", e, exc_info=True)
        return

    # Parse JSON { "summary": "..." } or fall back to raw text
    try:
        parsed = json.loads(raw)
        summary_text = parsed.get("summary", "").strip()
        if not summary_text:
            raise ValueError("Empty 'summary' field")
    except Exception:
        logger.warning("Could not parse JSON; using raw output")
        summary_text = raw.strip()

    # Create the summary turn as a "user" message
    summary_meta = {"turn": None, "finalized": True}
    summary_ut   = UnifiedTurn.create_turn(summary_meta, {"user": summary_text})

    # Assemble new history: [initial] + [summary] + kept body turns
    new_history = [initial_turn, summary_ut] + kept

    # Reindex all turns sequentially
    for idx, ut in enumerate(new_history):
        ut.turn_meta["turn"] = idx

    # Replace in-memory history and persist
    history.clear()
    history.extend(new_history)
    save_turns_list(agent_role, agent_id, repo_url)

    logger.info(
        "Summarized and pruned turns for %s/%s@%s [%s]: kept %d body turns + summary",
        agent_role, agent_id, repo_url, max_body_turns
    )


def _build_summary_prompt(turns: List[UnifiedTurn]) -> str:
    """
    Serialize only the assistant/tool messages from the pruned turns
    into a structured prompt for the summarization LLM.
    """
    lines: List[str] = []
    for turn in turns:
        idx = turn.turn_meta.get("turn")
        for role, msg in turn.messages.items():
            if role not in ("assistant", "tool"):
                continue
            content = msg.get("raw", {}).get("content", "")
            lines.append(f"[turn {idx}][{role}]: {content}")

    conversation = "\n".join(lines)
    instruction = (
        "Condense the above assistant and tool messages into a brief summary, "
        "capturing key facts and decisions.  Reply with valid JSON:\n"
        "{ \"summary\": \"<your summary here>\" }\n\n"
    )
    return instruction + conversation
