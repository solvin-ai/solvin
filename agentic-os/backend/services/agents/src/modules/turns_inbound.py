# modules/turns_inbound.py

"""
Parse and enrich LLM API responses into standardized message-centric records.

Supports multiple simultaneous tool invocations:
  - Wraps LLM output via centralized logic in unified_turn.py.
  - Extracts *all* tool_calls, enforces schema, computes hashes.
  - Returns lists "tools" and "tools_meta" rather than singletons.
  - Fetches the tools registry via modules.tool_registry_cache.get_tools_registry().
"""

import json
import logging
from pprint import pformat

from shared.logger import logger
from modules.unified_turn import _wrap_message, Role
from modules.turns_utils import parse_tool_arguments, compute_md5_hash

# instead of tools_info/tools_list, we get the registry from our cache
from modules.tool_registry_cache import get_tools_registry


def _filter_args_by_schema(input_args, json_schema):
    if not isinstance(input_args, dict):
        return input_args
    props = json_schema.get("properties")
    if not props or not isinstance(props, dict):
        return input_args
    allowed = set(props.keys())
    return {k: v for k, v in input_args.items() if k in allowed}


def _parse_assistant_message(raw_assistant):
    logger.debug("Wrapping assistant message: %s", raw_assistant)
    return _wrap_message(raw_assistant, Role.ASSISTANT.value)


def _parse_tool_message(raw_tool):
    logger.debug("Wrapping tool message: %s", raw_tool)
    # ensure shape { raw: {...} }
    if not (isinstance(raw_tool, dict) and "raw" in raw_tool):
        raw_tool = {"raw": raw_tool}
    return _wrap_message(raw_tool["raw"], Role.TOOL.value)


def parse_api_response(api_response, tools_registry=None):
    """
    Parse API response and return dict with keys:
      - assistant:        wrapped assistant message
      - tools:            list of wrapped tool messages (one per tool_call)
      - tools_meta:       list of metadata dicts (one per tool_call)
      - total_char_count: int
      - turn_meta:        { invocation_reason?: str, turns_to_purge: list[int] }
    """
    logger.debug("ENTER parse_api_response() with api_response: %s", pformat(api_response))

    assistant_raw = api_response.get("assistant", {}) or {}

    # 1) Fetch or reuse the tools registry (cached)
    if tools_registry is None:
        tools_registry = get_tools_registry()

    # 1a) Log a brief summary of the registry, not the full dump
    if logger.isEnabledFor(logging.DEBUG):
        if isinstance(tools_registry, dict) and "name" in tools_registry:
            entries = [tools_registry]
        elif isinstance(tools_registry, dict):
            entries = list(tools_registry.values())
        elif isinstance(tools_registry, list):
            entries = tools_registry
        else:
            entries = []
        names = [e.get("name") for e in entries if isinstance(e, dict) and "name" in e]
        logger.debug("tools_registry contains %d entries: %s", len(names), names)

    # 2) Wrap assistant message
    assistant_envelope = _parse_assistant_message(assistant_raw)

    # 3) Iterate all tool_calls
    tcalls = assistant_raw.get("tool_calls")
    if not isinstance(tcalls, list):
        tcalls = []

    tools_env = []
    tools_meta = []

    # Pre-flatten registry for lookup
    if isinstance(tools_registry, dict) and "name" in tools_registry:
        flat_registry = [tools_registry]
    elif isinstance(tools_registry, dict):
        flat_registry = list(tools_registry.values())
    elif isinstance(tools_registry, list):
        flat_registry = tools_registry
    else:
        flat_registry = []

    for tool_call in tcalls:
        # normalize call object
        if isinstance(tool_call.get("function"), dict):
            call_obj = tool_call["function"]
        else:
            call_obj = tool_call

        tool_name     = call_obj.get("name", "")
        arguments_str = call_obj.get("arguments", "") or ""
        call_id       = tool_call.get("id", "")

        logger.debug("Detected tool_call '%s' with args: %s", tool_name, arguments_str)

        # parse arguments JSON
        try:
            parsed_args, normalized_key = parse_tool_arguments(
                arguments_str, case_sensitive=False
            )
            if not isinstance(parsed_args, dict):
                raise ValueError("parsed_args not a dict")
        except Exception as e:
            logger.warning("parse_tool_arguments failed (%s); falling back to json.loads", e)
            try:
                parsed_args = json.loads(arguments_str or "{}")
            except Exception as ex:
                logger.error("json.loads failed for %r: %s", arguments_str, ex)
                parsed_args = {}
            normalized_key = ""

        # lookup schema & policy in the flattened registry
        preservation = None
        schema       = {}
        tool_obj     = None

        for entry in flat_registry:
            if entry.get("name") == tool_name:
                tool_obj = entry
                break

        if tool_obj:
            try:
                internal = tool_obj.get("internal", {})
                preservation = internal.get(
                    "preservation_policy",
                    tool_obj.get("preservation_policy")
                )
                schema = (
                    internal.get("schema")
                    or tool_obj.get("function", {}).get("parameters")
                    or tool_obj.get("schema")
                    or {}
                )
                if isinstance(schema, dict) and schema.get("properties"):
                    parsed_args = _filter_args_by_schema(parsed_args, schema)
            except Exception as e:
                logger.warning("Error processing registry for '%s': %s", tool_name, e)
        else:
            logger.warning("No registry entry for tool '%s'", tool_name)

        # compute args_hash for caching/filename hints
        if parsed_args:
            sorted_js = json.dumps(parsed_args, sort_keys=True)
            base      = tool_name.removeprefix("tool_")
            args_hash = compute_md5_hash(base + sorted_js)
        else:
            args_hash = "n/a"

        normalized_filename = normalized_key or ""

        meta = {
            "tool_name":           tool_name,
            "tool_call_id":        call_id,
            "input_args":          parsed_args,
            "preservation_policy": preservation,
            "normalized_args":     parsed_args,
            "args_hash":           args_hash,
            "normalized_filename": normalized_filename,
            "status":              "",    # to be filled later
            "execution_time":      0.0,   # to be filled later
            "deleted":             False,
            "rejection":           None,
        }

        raw_tool = {
            "role":          Role.TOOL.value,
            "name":          tool_name,
            "tool_call_id":  call_id,
            "content":       ""
        }
        tool_envelope = _parse_tool_message(raw_tool)

        content_str = str(tool_envelope["raw"].get("content") or "")
        tool_envelope["meta"]["char_count"] = len(content_str)

        tools_env.append(tool_envelope)
        tools_meta.append(meta)

    # 4) compute final char counts & return
    a_content = str(assistant_envelope["raw"].get("content") or "")
    assistant_envelope["meta"]["char_count"] = len(a_content)

    total = assistant_envelope["meta"]["char_count"] + sum(
        t["meta"]["char_count"] for t in tools_env
    )

    outbound = {
        "assistant":        assistant_envelope,
        "tools":            tools_env,
        "tools_meta":       tools_meta,
        "total_char_count": total,
    }

    # ----------------------------------------------------------------------------
    # Extract invocation_reason and turns_to_purge from the parsed tool arguments
    invocation_reason = None
    all_turns_to_purge = []
    for m in tools_meta:
        args = m.get("input_args", {})
        if invocation_reason is None and isinstance(args.get("invocation_reason"), str):
            invocation_reason = args["invocation_reason"]
        ttp = args.get("turns_to_purge")
        if isinstance(ttp, list):
            all_turns_to_purge.extend([t for t in ttp if isinstance(t, int)])

    turns_to_purge = sorted(set(all_turns_to_purge))

    outbound["turn_meta"] = {
        "invocation_reason": invocation_reason,
        "turns_to_purge":    turns_to_purge,
    }
    # ----------------------------------------------------------------------------

    logger.debug(
        "EXIT parse_api_response() → assistant.char_count=%d, tools_meta=%s, total_char_count=%d, turn_meta=%s",
        assistant_envelope["meta"].get("char_count", 0),
        tools_meta,
        total,
        outbound["turn_meta"],
    )
    return outbound


if __name__ == "__main__":
    # local smoke‐test
    test_api_response = {
        "assistant": {
            "role": "assistant",
            "content": "Example with run_bash",
            "tool_calls": [
                {
                  "id": "c1",
                  "function": {
                      "name": "run_bash",
                      "arguments": "{\"bash_command\":\"mvn clean compile\"}"
                  }
                }
            ],
        }
    }
    enriched = parse_api_response(test_api_response)
    print(json.dumps(enriched, indent=2))
