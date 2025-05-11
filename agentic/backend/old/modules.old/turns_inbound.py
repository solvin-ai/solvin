# modules/turns_inbound.py

"""
Revised UnifiedTurn API Response Processing (turns_inbound.py)

This module processes raw API responses from the LLM and enriches them by:
  • Delegating message wrapping to the centralized logic in unified_turn.py.
  • Extracting tool call details and enriching tool_meta (covering tool_name,
    input_args, preservation_policy, normalized_args, args_hash and normalized_filename).
  • Computing total_char_count as the sum of the wrapped assistant and tool message lengths.

Now, incoming messages are wrapped via the updated _wrap_message_updated function,
which preserves any extra fields in the original messages.
"""

import json
from pprint import pformat  # for pretty-printing in error messages

from modules.logs import logger
from modules.unified_turn import _wrap_message_updated, Role
from modules.turns_utils import parse_tool_arguments, compute_md5_hash

# ---------------------------------------------------------------------------
# New helper: Filter input arguments based on the JSON schema
# ---------------------------------------------------------------------------
def filter_args_by_schema(input_args, json_schema):
    """
    Filters the input_args dictionary based on the provided JSON schema.
    Only keys that are explicitly defined in the schema's "properties" will be retained.
    
    If input_args is not a dict or if the schema does not define any properties,
    the function returns input_args unchanged.
    """
    if not isinstance(input_args, dict):
        return input_args

    properties = json_schema.get("properties")
    if not properties or not isinstance(properties, dict):
        return input_args

    allowed_keys = set(properties.keys())
    filtered = { key: value for key, value in input_args.items() if key in allowed_keys }
    return filtered

# ---------------------------------------------------------------------------
# Message Wrapping Functions (Using the updated unified_turn wrapper)
# ---------------------------------------------------------------------------
def parse_assistant_message(raw_assistant):
    """
    Processes and wraps a raw assistant message using the updated unified_turn _wrap_message_updated.
    This ensures that all extra fields in the original message are preserved.
    """
    logger.debug("Processing raw assistant message using unified wrapper: %s", raw_assistant)
    return _wrap_message_updated(raw_assistant, Role.ASSISTANT.value)

def parse_tool_message(raw_tool):
    """
    Processes and wraps a raw tool message using the updated unified_turn _wrap_message_updated.
    This ensures that all extra fields in the original message are preserved.
    """
    logger.debug("Processing raw tool message using unified wrapper: %s", raw_tool)
    # Ensure the tool message is a dict with a "raw" key.
    if not (isinstance(raw_tool, dict) and "raw" in raw_tool):
        raw_tool = {"raw": raw_tool}
    return _wrap_message_updated(raw_tool["raw"], Role.TOOL.value)

# ---------------------------------------------------------------------------
# API Response Parsing and Enrichment
# ---------------------------------------------------------------------------
def parse_api_response(api_response, unified_registry=None):
    """
    Processes the raw API response and returns a dictionary with:
      • assistant: Wrapped assistant message envelope (using the unified wrapper).
      • tool: Wrapped tool message envelope.
      • tool_meta: Enriched tool metadata (excluding tool_call_id) containing:
           - tool_name
           - input_args
           - preservation_policy
           - normalized_args
           - args_hash
           - normalized_filename
      • total_char_count: Sum of the assistant and tool char_counts.

    When a tool call is detected in the assistant message:
      - Tool call details (such as function name and arguments) are extracted.
      - The function arguments are parsed using parse_tool_arguments (with a json.loads fallback).
      - When a tool is registered in unified_registry, its JSON schema is used to
        filter out any input arguments that are not listed in the schema.
      - An MD5 hash is computed from the sorted JSON string of the input_args.
      - normalized_filename is derived from the normalized arguments key.
    """
    logger.debug("ENTER parse_api_response() with api_response: %s", api_response)

    if unified_registry is None:
        try:
            from modules.tools_registry import get_global_registry
            unified_registry = get_global_registry()
        except Exception as e:
            logger.warning("Could not retrieve unified_registry: %s", e)
            unified_registry = {}

    original_assistant = api_response.get("assistant", {})
    tool_call = None
    if (original_assistant.get("tool_calls") and
        isinstance(original_assistant["tool_calls"], list) and
        len(original_assistant["tool_calls"]) > 0):
        tool_call = original_assistant["tool_calls"][0]

    assistant_envelope = parse_assistant_message(original_assistant)
    raw_tool = api_response.get("tool", {})

    enriched_tool_meta = {}
    arguments_str = ""
    if tool_call:
        tool_name = tool_call.get("function", {}).get("name", "")
        arguments_str = tool_call.get("function", {}).get("arguments", "")
        logger.debug("Tool call detected for tool '%s' with arguments: %s", tool_name, arguments_str)

        try:
            parsed_args, normalized_key = parse_tool_arguments(arguments_str, case_sensitive=False)
            if not isinstance(parsed_args, dict) or not parsed_args:
                raise ValueError("Empty or invalid parsed_args")
        except Exception as e:
            logger.warning("parse_tool_arguments failed (%s); using json.loads fallback", e)
            try:
                parsed_args = json.loads(arguments_str)
            except Exception as ex:
                logger.error("json.loads failed for arguments_str: %s", ex)
                parsed_args = {}
            normalized_key = ""

        logger.debug("Parsed arguments: %s", parsed_args)
        input_args = parsed_args

        preservation_policy = None
        schema = {}
        if unified_registry and tool_name in unified_registry:
            tool_obj = unified_registry[tool_name]
            logger.debug("tool_obj for %s: %s", tool_name, tool_obj)
            # Retrieve preservation policy from internal config or top-level.
            internal_config = tool_obj.get("internal", {})
            if "preservation_policy" in internal_config:
                preservation_policy = internal_config["preservation_policy"]
            elif "preservation_policy" in tool_obj:
                preservation_policy = tool_obj["preservation_policy"]
            else:
                raise ValueError("Preservation policy not found in tool object:\n" + pformat(tool_obj))
            logger.debug("Preservation policy: %s", preservation_policy)
            # Retrieve JSON schema.
            schema = internal_config.get("schema", tool_obj.get("function", {}).get("parameters", {}) or tool_obj.get("schema", {}))
            logger.debug("Retrieved JSON schema: %s", schema)
            if isinstance(schema, dict) and schema:
                logger.debug("Original input_args before filtering: %s", input_args)
                # Filter out any keys not defined in the schema.
                filtered_args = filter_args_by_schema(input_args, schema)
                logger.debug("Filtered args: %s", filtered_args)
                input_args = filtered_args

        normalized_args = input_args

        if normalized_args and len(normalized_args) > 0:
            sorted_json_str = json.dumps(normalized_args, sort_keys=True)
            stripped_tool_name = tool_name
            if stripped_tool_name.startswith("tool_"):
                stripped_tool_name = stripped_tool_name[len("tool_"):]
            args_hash = compute_md5_hash(stripped_tool_name + sorted_json_str)
        else:
            args_hash = "n/a"

        if normalized_key:
            normalized_filename = normalized_key if not isinstance(normalized_key, list) else normalized_key
        else:
            normalized_filename = ""

        enriched_tool_meta = {
            "tool_name": tool_name,
            "input_args": input_args,
            "preservation_policy": preservation_policy,
            "normalized_args": normalized_args,
            "args_hash": args_hash,
            "normalized_filename": normalized_filename
        }
        raw_tool["tool_call_id"] = tool_call.get("id", "")
        if not raw_tool.get("name"):
            raw_tool["name"] = tool_name
    else:
        raw_tool["tool_call_id"] = ""
        raw_tool["name"] = raw_tool.get("name", "")

    tool_envelope = parse_tool_message(raw_tool)

    # Compute character counts from the wrapped messages.
    assistant_content = str(assistant_envelope["raw"].get("content") or "")
    extra_length = len(arguments_str) if tool_call else 0
    assistant_envelope["meta"]["char_count"] = len(assistant_content) + extra_length

    tool_content = str(tool_envelope["raw"].get("content") or "")
    tool_envelope["meta"]["char_count"] = len(tool_content)

    total_char_count = assistant_envelope["meta"]["char_count"] + tool_envelope["meta"]["char_count"]

    outbound = {
        "assistant": assistant_envelope,
        "tool": tool_envelope,
        "tool_meta": enriched_tool_meta,
        "total_char_count": total_char_count
    }

    logger.debug("EXIT parse_api_response() with result: %s", outbound)
    return outbound

# ---------------------------------------------------------------------------
# Note: Functions for creating or updating UnifiedTurn instances have been moved to the unified_turn module.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Demonstration (for testing)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
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
              }],
              "extra_field": "preserve_this"
         },
         "tool": {
              "role": "tool",
              "content": "Directory tree created.",
              "additional_info": "keep this too"
         }
    }
    dummy_registry = {
         "tool_directory_tree": {
              "name": "tool_directory_tree",
              "description": (
                  "Generates a nested directory tree (directories only) as nested arrays, "
                  "but includes a directory only if it or one of its subdirectories contains "
                  "a source code file. Each directory is represented as [directory_name, "
                  "[child_directories]]. Returns a dictionary with a 'success' flag and an 'output' "
                  "containing the tree structure."
              ),
              "schema": {
                   "type": "object",
                   "properties": {
                        "path": {
                             "type": "string",
                             "description": "Starting directory (defaults to '.'). If relative, resolved against SANDBOX_REPO_ROOT.",
                             "default": "."
                        },
                        "max_depth": {
                             "type": "integer",
                             "description": "Maximum recursion depth (0 means no limit).",
                             "default": 0
                        }
                   },
                   "required": [],
                   "additionalProperties": False,
                   "strict": True
              },
              "preservation_policy": "one-of",
              "type": "readonly",
              "executor": lambda **kwargs: "dummy result"
         }
    }
    enriched = parse_api_response(test_api_response, unified_registry=dummy_registry)
    print("Enriched API Response:")
    print(json.dumps(enriched, indent=2))
