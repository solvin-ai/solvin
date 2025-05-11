# modules/unified_turn.py

"""
Unified Turn Module

Defines UnifiedTurn, a grouping of messages into a single “turn”:
  • turn_meta: { turn: int, finalized: bool, total_char_count: int }
  • tool_meta: tool‐call metadata (status, execution_time, rejection, etc)
  • messages:  dict of role→{ raw: {role, content, …}, meta: {timestamp, original_message_id, char_count, …} }

This module has no knowledge of LLM APIs or HTTP clients—it only knows how to
wrap raw messages of arbitrary roles and maintain per-turn state.
"""

import json
import datetime
from enum import Enum
from typing import Any, Dict


class Role(Enum):
    SYSTEM    = "system"
    DEVELOPER = "developer"
    USER      = "user"
    ASSISTANT = "assistant"
    TOOL      = "tool"


class PreservationPolicy(Enum):
    ONE_TIME     = "one-time"
    UNTIL_BUILD  = "until-build"
    UNTIL_UPDATE = "until-update"
    ONE_OF       = "one-of"
    ALWAYS       = "always"
    BUILD        = "build"


class StrictDict(dict):
    """A dict that forbids missing-key access."""
    def __getitem__(self, key):
        if key not in self:
            raise KeyError(f"Key '{key}' is required but missing in StrictDict")
        return super().__getitem__(key)
    def __getattr__(self, key):
        return self[key]
    def __setattr__(self, key, value):
        self[key] = value


class UnifiedTurn:
    __slots__ = ("turn_meta", "tool_meta", "messages")

    def __init__(
        self,
        turn_meta: Dict[str, Any],
        tool_meta: Dict[str, Any],
        messages: Dict[str, Any],
    ):
        self.turn_meta = turn_meta
        self.tool_meta = tool_meta
        self.messages  = messages

    def __repr__(self):
        t = self.turn_meta.get("turn", "?")
        main = next(iter(self.messages), "?")
        return f"<UnifiedTurn turn={t} main={main}>"

    def __str__(self):
        return json.dumps({
            "turn_meta": self.turn_meta,
            "tool_meta": self.tool_meta,
            "messages":  self.messages,
        }, indent=2)

    def add_message(self, role: str, content: str, original_message_id: int):
        """
        Inject a new message *into the same turn* under `role`, using the
        provided original_message_id.  Multiple messages of the same role
        will be keyed by "<role>.<id>" to avoid collisions.
        """
        # build raw dict
        raw = {"role": role, "content": content}

        # timestamp & char count
        ts = datetime.datetime.utcnow().isoformat() + "Z"
        char_count = len(str(content))

        meta = {
            "timestamp":            ts,
            "original_message_id":  original_message_id,
            "char_count":           char_count,
        }

        key = f"{role}.{original_message_id}"
        self.messages[key] = {"raw": raw, "meta": meta}

        # bump total_char_count in turn_meta
        prev = self.turn_meta.get("total_char_count", 0)
        self.turn_meta["total_char_count"] = prev + char_count

    @classmethod
    def create_turn(
        cls,
        meta: Dict[str, Any],
        raw_messages: Dict[str, Any]
    ) -> "UnifiedTurn":
        """
        Build a UnifiedTurn from:
          • meta: { turn: int, finalized?: bool, total_char_count?: int, tool_meta?: dict }
          • raw_messages: mapping role→either
                – a dict with 'raw' and 'meta' (preserves exactly)
                – or a raw value (str, dict, etc.) which will be wrapped with
                  a placeholder original_message_id=None
        """
        turn_number = int(meta.get("turn", 0))

        # Normalize every provided role/msg
        messages: Dict[str, Any] = {}
        for role, msg in raw_messages.items():
            if isinstance(msg, dict) and "raw" in msg and "meta" in msg:
                messages[role] = msg
            else:
                messages[role] = _wrap_message(msg, role)

        # Compute total_char_count if missing
        tcc = meta.get("total_char_count")
        if tcc is None:
            tcc = sum(m["meta"]["char_count"] for m in messages.values())

        turn_meta = {
            "turn":             turn_number,
            "finalized":        bool(meta.get("finalized", True)),
            "total_char_count": tcc,
        }

        # tool_meta defaults
        raw_tool_meta = meta.get("tool_meta") or {}
        tool_meta = raw_tool_meta.copy()
        tool_meta.setdefault("status",        "")
        tool_meta.setdefault("execution_time", 0.0)
        tool_meta.setdefault("deleted",       False)
        tool_meta.setdefault("rejection",     None)

        return cls(turn_meta, tool_meta, messages)


def _wrap_message(message: Any, expected_role: str) -> Dict[str, Any]:
    """
    Normalize any raw message into the shape:
      {
        "raw": { "role": expected_role, "content": str(...) },
        "meta": { "timestamp": "...Z", "original_message_id": None, "char_count": int }
      }
    (We no longer bump an in-process counter here; callers like append_messages()
     must allocate a real ID and then use add_message() to overwrite the placeholder.)
    """
    # build raw
    if isinstance(message, dict) and "raw" in message:
        raw = message["raw"].copy()
    elif isinstance(message, dict) and "content" in message:
        raw = message.copy()
    else:
        raw = {"content": str(message)}

    raw.setdefault("role", expected_role)
    raw.setdefault("content", "")

    ts = datetime.datetime.utcnow().isoformat() + "Z"
    char_count = len(str(raw["content"]))

    meta = {
        "timestamp":           ts,
        "original_message_id": None,
        "char_count":          char_count,
    }
    return {"raw": raw, "meta": meta}


# If run standalone, a quick smoke‐test follows
if __name__ == "__main__":
    # Turn‐0 with two initial messages
    ut0 = UnifiedTurn.create_turn(
        {"turn": 0, "finalized": True, "tool_meta": {}, "total_char_count": 0},
        {
          "system":    {"raw": {"role": "system",    "content": "SYS"}, "meta": {"timestamp": "", "original_message_id":0, "char_count":3}},
          "developer": {"raw": {"role": "developer", "content": "DEV"}, "meta": {"timestamp": "", "original_message_id":1, "char_count":3}},
        }
    )
    print(ut0)

    # Now inject two user messages with real IDs
    ut0.add_message("user", "Hello!", original_message_id=42)
    ut0.add_message("user", "World!", original_message_id=43)
    print(ut0)