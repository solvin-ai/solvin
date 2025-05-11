# modules/unified_turn.py

"""
Unified Turn and Tool Module

This module defines the UnifiedTurn object as a simple data container for conversation turns.
It also provides related enumerations and a StrictDict implementation that raises errors when
attempting to access undefined keys.

The expected UnifiedTurn data structure is:

{
  "turn_meta": {
    "turn": (int),
    "finalized": (bool),
    "total_char_count": (int)
  },
  "tool_meta": {
    "tool_name": (str),
    "execution_time": (float),
    "pending_deletion": (bool),
    "deleted": (bool),
    "rejection": (nullable),
    "status": (str),
    "args_hash": (str),
    "preservation_policy": (str),
    "input_args": (dict),
    "normalized_args": (str),
    "normalized_filename": (str)
  },
  "messages": {
    <message_key>: {
      "meta": {
         "timestamp": (ISO8601 str),
         "original_message_id": (int),
         "char_count": (int)
      },
      "raw": { … }   ← Contains the complete original message without dropping extra fields
    },
    ...
  }
}

New Features:
• UnifiedTurn.create_from_api – Create a UnifiedTurn directly from a raw API response.
• UnifiedTurn.update_from_api – Update an existing UnifiedTurn instance with API-enriched data.

NOTE: The internal message wrapper (_wrap_message_updated) has been updated. Instead of re‑constructing the message to only include “role” and “content”, it now copies over every field from the original message.
"""

import json
import datetime
from enum import Enum

########################################################################
# Enumerations
########################################################################
class Role(Enum):
    ASSISTANT = "assistant"
    TOOL = "tool"
    USER = "user"
    DEVELOPER = "developer"

class PreservationPolicy(Enum):
    ONE_TIME = "one-time"
    UNTIL_BUILD = "until-build"
    UNTIL_UPDATE = "until-update"
    ONE_OF = "one-of"
    ALWAYS = "always"
    BUILD = "build"

########################################################################
# StrictDict Implementation
########################################################################
class StrictDict(dict):
    """
    A strict dictionary that raises an error when attempting to access a key that does not exist.
    """
    def __getitem__(self, key):
        if key not in self:
            raise KeyError(f"Key '{key}' does not exist in StrictDict")
        return super().__getitem__(key)

    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self[key] = value

########################################################################
# UnifiedTurn Class (Container Only)
########################################################################
class UnifiedTurn:
    __slots__ = ["turn_meta", "tool_meta", "messages"]

    def __init__(self, turn_meta: dict, tool_meta: dict, messages: dict):
        """
        Constructs a UnifiedTurn instance.

        It assumes that the provided dictionaries have already been enriched by external logic.

        turn_meta must include: "turn", "finalized", "total_char_count".
        tool_meta must include: "tool_name", "execution_time", "pending_deletion",
            "deleted", "rejection", "status", "args_hash", "preservation_policy",
            "input_args", "normalized_args", and "normalized_filename".
        messages is a dict keyed by roles (e.g. {"assistant", "tool"} or {"developer", "user"}).
        """
        self.turn_meta = turn_meta
        self.tool_meta = tool_meta
        self.messages = messages

    def __str__(self):
        return json.dumps({
            "turn_meta": self.turn_meta,
            "tool_meta": self.tool_meta,
            "messages": self.messages,
        }, indent=2)

    def __repr__(self):
        primary_role = (self.messages.get("assistant", {}).get("raw", {}).get("role") or
                        self.messages.get("developer", {}).get("raw", {}).get("role", "unknown"))
        return f"<UnifiedTurn turn={self.turn_meta.get('turn')}, role={primary_role}>"

    @classmethod
    def create_turn(cls, meta: dict, raw_messages: dict, tool_meta_override: dict = None) -> 'UnifiedTurn':
        """
        Factory method to create a UnifiedTurn instance.

        It enforces the unified structure by:
          • Determining the expected roles based on the turn number.
             For turn 0, it normally expects "developer" and "user" but if a "system" message is provided, it is included.
             For later turns, it expects "assistant" and "tool".
          • Wrapping messages using the internal _wrap_message_updated function if they are not already wrapped.
          • Calculating the total character count if not provided.
          • Enforcing allowed dynamic fields for tool_meta (i.e. "status", "execution_time", "deleted", "rejection").

        Parameters:
          meta            : A dictionary that may include "turn", "finalized", and optionally "tool_meta" and other allowed keys.
          raw_messages    : A dictionary containing the raw messages keyed by role.
                            For turn 0 it should have keys "developer" and "user" (and optionally "system"),
                            otherwise "assistant" and "tool".
          tool_meta_override (optional): A dict with any dynamic tool_meta fields to override.

        Returns:
          A UnifiedTurn instance.
        """
        turn_number = meta.get("turn", 0)
        if turn_number == 0:
            # For turn 0 normally expect developer and user.
            expected_roles = ["developer", "user"]
            # If a system message is provided, add it at the beginning.
            if "system" in raw_messages:
                expected_roles.insert(0, "system")
        else:
            expected_roles = ["assistant", "tool"]

        conformed_messages = {}
        for r in expected_roles:
            # If the message is already wrapped (contains both "meta" and "raw"), leave as is.
            if isinstance(raw_messages.get(r), dict) and "meta" in raw_messages[r] and "raw" in raw_messages[r]:
                conformed_messages[r] = raw_messages[r]
            else:
                # Use the internal message wrapper.
                conformed_messages[r] = _wrap_message_updated(raw_messages.get(r), r)

        # Calculate total_char_count if not provided.
        if "total_char_count" in meta:
            total_char_count = meta["total_char_count"]
        else:
            total_char_count = sum(conformed_messages[r]["meta"]["char_count"] for r in expected_roles)

        turn_meta_final = {
            "turn": meta.get("turn", 0),
            "finalized": meta.get("finalized", False),
            "total_char_count": total_char_count
        }

        # Prepare tool_meta. Allowed dynamic fields include: "status", "execution_time", "deleted", "rejection".
        tool_meta = meta.get("tool_meta", {}).copy()
        allowed_keys = ["status", "execution_time", "deleted", "rejection"]
        for key in allowed_keys:
            if key in meta:
                tool_meta[key] = meta[key]
        if tool_meta_override:
            for key in allowed_keys:
                if key in tool_meta_override:
                    tool_meta[key] = tool_meta_override[key]

        return cls(turn_meta_final, tool_meta, conformed_messages)

    @classmethod
    def create_from_api(cls, turn_number, api_response, tool_meta_override=None, unified_registry=None) -> 'UnifiedTurn':
        """
        Factory method to create a UnifiedTurn instance from a raw API response.
        This method leverages API response parsing to enrich messages and tool metadata.

        Parameters:
          turn_number       : The turn number for this conversation turn.
          api_response      : The raw API response from the LLM.
          tool_meta_override: (Optional) A dictionary with any dynamic tool_meta fields to override.
          unified_registry  : (Optional) A registry for tool configurations.

        Returns:
          A UnifiedTurn instance populated with data from the API response.
        """
        # Lazy import to avoid circular dependencies.
        from modules.turns_inbound import parse_api_response
        inbound = parse_api_response(api_response, unified_registry)
        total_char_count = inbound.get("total_char_count", 0)
        turn_meta = {
            "turn": turn_number,
            "finalized": False,
            "total_char_count": total_char_count
        }
        enriched = inbound.get("tool_meta", {})
        full_tool_meta = {
            "tool_name": enriched.get("tool_name", ""),
            "input_args": enriched.get("input_args", {}),
            "preservation_policy": enriched.get("preservation_policy", ""),
            "normalized_args": enriched.get("normalized_args", {}),
            "args_hash": enriched.get("args_hash", ""),
            "normalized_filename": enriched.get("normalized_filename", ""),
            "status": "n/a",
            "execution_time": 0.0,
            "deleted": False,
            "rejection": None
        }
        if tool_meta_override:
            for key in ["finalized", "status", "turn", "execution_time", "deleted", "rejection"]:
                if key in tool_meta_override:
                    full_tool_meta[key] = tool_meta_override[key]
        messages = {
            "assistant": inbound["assistant"],
            "tool": inbound["tool"]
        }
        new_turn = cls(turn_meta, full_tool_meta, messages)
        new_turn.turn_meta["total_char_count"] = total_char_count
        return new_turn

    def update_from_api(self, api_response, unified_registry=None):
        """
        Updates the existing UnifiedTurn instance with API-enriched data from a raw API response.
        Only allowed fields (e.g., messages and total_char_count) are updated in this method.

        Parameters:
          api_response     : The raw API response from the LLM.
          unified_registry : (Optional) A registry for tool configurations.
        """
        from modules.turns_inbound import parse_api_response
        inbound = parse_api_response(api_response, unified_registry)
        self.messages["assistant"] = inbound["assistant"]
        self.messages["tool"] = inbound["tool"]
        self.turn_meta["total_char_count"] = inbound.get("total_char_count", 0)
        for key, value in inbound.get("tool_meta", {}).items():
            self.tool_meta[key] = value

########################################################################
# Internal Message Wrapping Function and Counter
########################################################################
_MESSAGE_ID_COUNTER = 0

def _wrap_message_updated(message, expected_role):
    """
    Wraps a message into the unified message schema using nested 'meta' and 'raw' keys.
    Unlike previous implementations, this version preserves extra fields present in the original message.
    If the message is not already wrapped, it creates an envelope containing:
      - "raw": the original message (preserving all keys).
      - "meta": metadata including timestamp, original_message_id, and char_count.

    Parameters:
      message         : The original message (typically a dict, but may be another type).
      expected_role   : The role to assign if not already present in the message.

    Returns:
      A dictionary with keys "meta" and "raw", where "raw" is a (possibly copied) original message.
    """
    global _MESSAGE_ID_COUNTER
    if isinstance(message, dict):
        if "raw" in message:
            raw = message["raw"].copy()
        else:
            raw = message.copy()
        raw.setdefault("role", expected_role)
        raw.setdefault("content", "")
        content = raw.get("content") or ""
    else:
        raw = {"role": expected_role, "content": str(message)}
        content = raw["content"]
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    message_id = _MESSAGE_ID_COUNTER
    _MESSAGE_ID_COUNTER += 1
    char_count = len(str(content))
    meta = {"timestamp": timestamp, "original_message_id": message_id, "char_count": char_count}
    return {"meta": meta, "raw": raw}

########################################################################
# UnifiedTool and ToolsRegistry (For Tool Registration)
########################################################################
class UnifiedTool:
    def __init__(self, name, executor, internal, description, schema):
        self.name = name
        self.executor = executor
        self.internal = internal
        self.description = description
        self.schema = schema

    def __repr__(self):
        return f"<UnifiedTool {self.name}>"

class ToolsRegistry:
    def __init__(self, tools_list=None):
        self._tools = {tool.name: tool for tool in (tools_list or [])}

    def register_tool(self, tool):
        self._tools[tool.name] = tool

    def get_tool(self, tool_name):
        return self._tools.get(tool_name)

    def list_tools(self):
        return list(self._tools.values())

    def __contains__(self, tool_name):
        return tool_name in self._tools

    def __getitem__(self, tool_name):
        if tool_name in self._tools:
            return self._tools[tool_name]
        raise KeyError(f"Tool '{tool_name}' not found in ToolsRegistry")

    def __repr__(self):
        return f"ToolsRegistry({self._tools})"

########################################################################
# __main__ Demonstration
########################################################################
if __name__ == "__main__":
    # -----------------------------
    # Part 1: Testing UnifiedTurn instantiation via factory method
    # -----------------------------
    print("Testing UnifiedTurn instantiation via create_turn:")
    example_meta = {
        "turn": 0,
        "finalized": True,
        "tool_meta": {},
    }
    example_raw_messages = {
        "system": {"raw": {"role": "system", "content": "System directive: please produce json responses."}},
        "developer": {"raw": {"role": "developer", "content": "Initial directive", "extra": "keep this"}},
        "user": {"raw": {"role": "user", "content": "User message", "details": "retain all"}}
    }
    ut = UnifiedTurn.create_turn(example_meta, example_raw_messages)
    print("UnifiedTurn object dump:")
    print(ut)

    # -----------------------------
    # Part 2: Demonstrating ToolsRegistry integration using the global tools registry.
    # -----------------------------
    print("\nTesting ToolsRegistry creation with global tools registry:")

    try:
        from modules.tools_registry import initialize_global_registry
    except ImportError as e:
        print("Error importing tools_registry module:", e)
        global_tools_dict = {}
    else:
        global_tools_dict = initialize_global_registry(run_in_container=False)

    if global_tools_dict:
        tools_list = []
        for record in global_tools_dict.values():
            tool_obj = UnifiedTool(
                name=record["name"],
                executor=record["executor"],
                internal={
                    "type": record["type"],
                    "preservation_policy": record["preservation_policy"]
                },
                description=record["description"],
                schema=record["schema"]
            )
            tools_list.append(tool_obj)
        registry = ToolsRegistry(tools_list)
        print("Registered tools:", registry.list_tools())
    else:
        print("No tools discovered.")

    # -----------------------------
    # Part 3: Testing UnifiedTurn creation from API response.
    # -----------------------------
    print("\nTesting UnifiedTurn creation from API response:")
    test_api_response = {
         "assistant": {
              "role": "assistant",
              "content": "Please generate a directory tree.",
              "tool_calls": [{
                    "id": "call_test_123",
                    "function": {
                         "name": "tool_directory_tree",
                         "arguments": "{\"path\": \".\", \"max_depth\": 3, \"randomArg\": \"foo\"}"
                    },
                    "type": "function"
              }]
         },
         "tool": {
              "role": "tool",
              "content": "Directory tree created."
         }
    }
    ut_api = UnifiedTurn.create_from_api(1, test_api_response)
    print("UnifiedTurn created from API response:")
    print(ut_api)

    # -----------------------------
    # Part 4: Testing UnifiedTurn update from API response.
    # -----------------------------
    print("\nTesting UnifiedTurn update from API response:")
    updated_api_response = {
         "assistant": {
              "role": "assistant",
              "content": "Updated directive.",
              "tool_calls": [{
                    "id": "call_test_456",
                    "function": {
                         "name": "tool_directory_tree",
                         "arguments": "{\"path\": \".\", \"max_depth\": 2}"
                    },
                    "type": "function"
              }]
         },
         "tool": {
              "role": "tool",
              "content": "Directory tree updated."
         }
    }
    ut_api.update_from_api(updated_api_response)
    print("UnifiedTurn after update from API response:")
    print(ut_api)
