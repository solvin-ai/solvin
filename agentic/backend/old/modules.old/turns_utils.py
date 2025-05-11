# modules/turns_utils.py

"""
Helpers for turn management and tool utilities.

This module provides functions to:
  • Produce unique message IDs.
  • Verify that a message is a valid UnifiedTurn.
  • Merge an assistant message and its tool response into a unified turn.
  • Manage tool call arguments (parsing, normalization, MD5 hashing, etc).
  • Perform file system and subprocess management (grouping paths, backing up files, etc).
"""

import os
import json
import shutil
import subprocess
import hashlib
import base64
from pprint import pformat
from datetime import datetime

from modules.unified_turn import UnifiedTurn
from modules.logs import logger
from modules.tools_safety import check_path, SANDBOX_DIR, SANDBOX_REPOS_ROOT

# ---------------------------
# Turn Management Functions
# ---------------------------
_message_counter = 0

def get_next_message_id() -> int:
    """
    Returns the next unique message identifier.
    
    This is implemented via a module-level counter.
    """
    global _message_counter
    _message_counter += 1
    return _message_counter

def ensure_unified_turn(msg: any) -> UnifiedTurn:
    """
    Ensures the provided message is a UnifiedTurn with a correctly nested messages dict.

    A valid messages dictionary must have one of these key sets:
      • {"assistant", "tool"} for non–turn-0 messages.
      • {"developer", "user"} for turn-0 messages.
    Furthermore, for each key the associated value must be a dict containing a 'raw'
    field whose own dictionary includes at least the keys "role" and "content".

    Parameters:
        msg: The message object to validate.

    Returns:
        The message if it is a valid UnifiedTurn.

    Raises:
        ValueError or TypeError if the message does not meet requirements.
    """
    if isinstance(msg, UnifiedTurn):
        raw = msg.messages
        if not isinstance(raw, dict):
            raise ValueError("UnifiedTurn messages must be a dictionary. Dump:\n" + repr(msg))
        allowed_key_sets = [{"assistant", "tool"}, {"developer", "user"}]
        if set(raw.keys()) not in allowed_key_sets:
            raise ValueError(
                "UnifiedTurn messages must be nested using one of these key sets: "
                "{'assistant', 'tool'} or {'developer', 'user'}. Dump:\n" + repr(msg)
            )
        for key, value in raw.items():
            if not (isinstance(value, dict) and "raw" in value):
                raise ValueError(
                    f"UnifiedTurn message for key '{key}' must be a dict containing a 'raw' field. Dump:\n" + repr(value)
                )
            raw_value = value["raw"]
            if not (isinstance(raw_value, dict) and "role" in raw_value and "content" in raw_value):
                raise ValueError(
                    f"UnifiedTurn raw dict for '{key}' must contain 'role' and 'content'. Dump:\n" + repr(raw_value)
                )
        return msg
    elif isinstance(msg, dict):
        raise ValueError("Detected a message dict; all messages should be UnifiedTurn objects.")
    else:
        raise TypeError("Unsupported message type passed to ensure_unified_turn. Dump:\n" + repr(msg))

def commit_message_pair(assistant_message, tool_message):
    """
    Merges an assistant message and its tool response into a single UnifiedTurn,
    and appends it to the global turns list.

    The unified turn structure is as follows:

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
           "input_args": (dict)
        },
        "messages": {
           "assistant": {
              "meta": {
                 "timestamp": (ISO8601 str),
                 "original_message_id": (int),
                 "char_count": (int)
              },
              "raw": (dict)  // assistant message payload
           },
           "tool": {
              "meta": {
                 "timestamp": (ISO8601 str),
                 "original_message_id": (int),
                 "char_count": (int)
              },
              "raw": (dict)  // tool message payload
           }
        }
      }

    This function automatically retrieves the global turns list (via modules.turns_list)
    for the currently active agent, merges the two messages into a unified turn,
    and appends that turn to the list.
    """
    from modules.turns_list import get_turns_list, append_turn

    global_turns = get_turns_list()

    # Determine the turn number based on the last turn (if any)
    if global_turns:
        last_turn = global_turns[-1].turn_meta.get("turn", 0)
        turn_number = last_turn + 1
    else:
        turn_number = 0

    now = datetime.utcnow().isoformat() + "Z"
    assistant_ts = assistant_message.meta.get("timestamp", now)
    tool_ts = tool_message.meta.get("timestamp", now)

    assistant_content = assistant_message.raw_messages.get("content", "")
    tool_content = tool_message.raw_messages.get("content", "")
    assistant_char_count = len(assistant_content)
    tool_char_count = len(tool_content)
    total_char_count = assistant_char_count + tool_char_count

    turn_meta = {
        "turn": turn_number,
        "finalized": True,
        "total_char_count": total_char_count
    }

    input_args = assistant_message.meta.get("input_args", {})
    normalized_args = input_args if isinstance(input_args, dict) else {}
    normalized_args_str = normalize_tool_arguments(normalized_args) if isinstance(normalized_args, dict) else ""
    tool_meta = {
        "tool_name": assistant_message.meta.get("tool_name", ""),
        "execution_time": 0.0,
        "pending_deletion": False,
        "deleted": False,
        "rejection": None,
        "status": "success",
        "args_hash": compute_md5_hash(normalized_args_str),
        "preservation_policy": "",
        "input_args": input_args
    }

    unified_messages = {
        "assistant": {
            "meta": {
                "timestamp": assistant_ts,
                "original_message_id": assistant_message.message_id,
                "char_count": assistant_char_count
            },
            "raw": assistant_message.raw_messages
        },
        "tool": {
            "meta": {
                "timestamp": tool_ts,
                "original_message_id": tool_message.message_id,
                "char_count": tool_char_count
            },
            "raw": tool_message.raw_messages
        }
    }

    unified_turn = UnifiedTurn(turn_meta, tool_meta, unified_messages)
    # Retrieve active agent info before appending the turn.
    from modules.turns_list import get_active_agent
    agent_role, agent_id = get_active_agent()
    append_turn(agent_role, agent_id, unified_turn)

# ---------------------------
# Tool Utilities and File/System Functions
# ---------------------------
FILE_ARG_KEYS = ["file_path", "file_paths", "filename", "target", "repo_path", "path"]

def extract_all_normalized_file_keys(args, case_sensitive: bool = False):
    """
    Recursively traverses the tool arguments (up to a 2nd level) to
    extract all file path values using common keys.

    Parameters:
        args (dict): Parsed tool arguments.
        case_sensitive (bool): If True, the returned paths keep their original case.

    Returns:
        list: A list of normalized file paths (each normalized using os.path.normpath).
    """
    files = []

    def add_value(val):
        normalized = os.path.normpath(str(val)).strip()
        if not case_sensitive:
            normalized = normalized.lower()
        if normalized and normalized not in files:
            files.append(normalized)

    if not isinstance(args, dict):
        return files

    # Check top-level keys.
    for key in FILE_ARG_KEYS:
        if key in args and args[key]:
            value = args[key]
            if key == "file_paths" and isinstance(value, list):
                for item in value:
                    add_value(item)
            else:
                add_value(value)

    # Check one level deep (e.g. inside lists or nested dictionaries).
    for v in args.values():
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    for key in FILE_ARG_KEYS:
                        if key in item and item[key]:
                            nested_value = item[key]
                            if key == "file_paths" and isinstance(nested_value, list):
                                for it in nested_value:
                                    add_value(it)
                            else:
                                add_value(nested_value)
        elif isinstance(v, dict):
            for key in FILE_ARG_KEYS:
                if key in v and v[key]:
                    nested_value = v[key]
                    if key == "file_paths" and isinstance(nested_value, list):
                        for it in nested_value:
                            add_value(it)
                    else:
                        add_value(nested_value)
    return files

def parse_tool_arguments(arg_str, case_sensitive: bool = False):
    """
    Parses a JSON string representing tool arguments.

    Parameters:
        arg_str (str): JSON string of tool arguments.
        case_sensitive (bool): If True, the argument values keep their original case.

    Returns:
        tuple: (parsed_arguments (dict), normalized_key (str or list))

    The normalized_key is determined by checking for common file argument keys (e.g. "file_path", "file_paths", etc.)
    both at the top level and one level deep. When multiple file-related values are found, the normalized_key is returned
    as a list; if exactly one is found, it is returned as a string. If no file-related key is found, an empty string ("")
    is returned.
    """
    try:
        args = json.loads(arg_str)
    except Exception as e:
        logger.warning("JSON parsing error (%s); defaulting to empty dict.", e)
        args = {}

    normalized_key = ""
    if isinstance(args, dict):
        file_keys_found = extract_all_normalized_file_keys(args, case_sensitive=case_sensitive)
        if file_keys_found:
            normalized_key = file_keys_found[0] if len(file_keys_found) == 1 else file_keys_found
        else:
            normalized_key = ""
    else:
        normalized_key = ""
    return args, normalized_key

def get_normalized_file_key(arguments_str, case_sensitive: bool = False):
    """
    Returns a normalized key for tool arguments by delegating to parse_tool_arguments.
    The return value may be a string (if only one file path is found), a list (if multiple are found), or
    an empty string if no file-related key is discovered.

    Parameters:
        arguments_str (str): A JSON string representing tool arguments.
        case_sensitive (bool): Determines if normalization is case-sensitive.

    Returns:
        str or list: The normalized file identifier(s) based on file-related arguments.
    """
    _, key = parse_tool_arguments(arguments_str, case_sensitive=case_sensitive)
    return key

def normalize_tool_arguments(args, json_schema=None):
    """
    Normalizes and filters a tool call's arguments.

    If a json_schema is provided, only the allowed keys are kept.
    The output is a consistently sorted JSON string.

    Parameters:
        args (dict): The tool call's arguments.
        json_schema (dict, optional): The JSON schema defining allowed keys.

    Returns:
        str: Sorted JSON string of filtered arguments.
    """
    logger.trace("normalize_tool_arguments: original args = %s", args)
    if json_schema:
        try:
            logger.trace("normalize_tool_arguments: received json_schema = %s", json.dumps(json_schema))
        except Exception:
            logger.trace("normalize_tool_arguments: received json_schema (non-serializable)")
    else:
        logger.debug("normalize_tool_arguments: received json_schema = None")

    if json_schema is None:
        normalized = json.dumps(args, sort_keys=True)
        logger.trace("normalize_tool_arguments: normalized output = %s", normalized)
        return normalized

    # Determine allowed keys: support common schema definitions.
    if isinstance(json_schema, dict) and not any(key in json_schema for key in ["parameters", "properties"]):
        allowed = json_schema
    elif "parameters" in json_schema and isinstance(json_schema["parameters"], dict):
        allowed = json_schema["parameters"].get("properties", {})
    elif "properties" in json_schema:
        allowed = json_schema.get("properties", {})
    elif "parameters" in json_schema:
        allowed = json_schema["parameters"]
    else:
        allowed = {}

    logger.debug("normalize_tool_arguments: extracted allowed keys = %s", list(allowed.keys()) if allowed else "None")

    filtered = {k: args[k] for k in allowed.keys() if k in args}
    normalized = json.dumps(filtered, sort_keys=True)
    logger.trace("normalize_tool_arguments: normalized output = %s", normalized)
    return normalized

def get_tool_internal(tool_definition):
    """
    Retrieves the internal configuration for a tool.

    Parameters:
        tool_definition: Either a callable with an "internal" attribute or a dict with key "internal".

    Returns:
        dict: The tool's internal configuration.
    """
    if callable(tool_definition):
        return tool_definition.internal
    return tool_definition["internal"]

def get_tool_policy_from_definition(tool_definition):
    """
    Retrieves the preservation policy from a tool's internal configuration.

    Parameters:
        tool_definition: The tool definition.

    Returns:
        The preservation policy value.
    """
    return get_tool_internal(tool_definition)["preservation_policy"]

def normalize_policy(policy):
    """
    Normalizes a policy string by replacing varied dash characters and lowercasing.

    Parameters:
        policy (str): Original policy string.

    Returns:
        str: Normalized policy.
    """
    if not policy:
        return ""
    for dash in ["\u2011", "\u2013", "\u2014"]:
        policy = policy.replace(dash, "-")
    return policy.lower().strip()

def is_tool_mutating(tool_definition):
    """
    Checks if a tool is mutating by inspecting its internal "type" property.

    Parameters:
        tool_definition: The tool definition.

    Returns:
        bool: True if the tool is mutating; otherwise False.
    """
    return get_tool_internal(tool_definition)["type"].lower() == "mutating"

def should_persist_until_build(tool_definition):
    """
    Determines if a tool's preservation policy is UNTIL_BUILD.

    Parameters:
        tool_definition: The tool definition.

    Returns:
        bool: True if the preservation policy equals UNTIL_BUILD.
    """
    from modules.unified_turn import PreservationPolicy
    normalized_policy = normalize_policy(get_tool_internal(tool_definition)["preservation_policy"])
    return normalized_policy == PreservationPolicy.UNTIL_BUILD.value

def compute_md5_hash(arg_str):
    """
    Computes an MD5 hash (base64 encoded without trailing "=") for the given string.

    Parameters:
        arg_str (str): Input string.

    Returns:
        str: The computed MD5 hash, or an empty string if the input is trivial.
    """
    stripped = arg_str.strip()
    if stripped in ("", "{}"):
        return ""
    try:
        digest = hashlib.md5(arg_str.encode("utf-8")).digest()
        args_hash = base64.b64encode(digest).decode("utf-8")
        return args_hash.rstrip("=")
    except Exception as exc:
        logger.error("Error computing MD5 hash for tool arguments: %s", exc)
        return ""

def get_file_identifier(args_dict, case_sensitive: bool = False):
    """
    Extracts a normalized file identifier from tool arguments.

    Checks for any key in FILE_ARG_KEYS and returns its normalized value,
    falling back to other common keys if necessary.

    Parameters:
        args_dict (dict): Tool arguments.
        case_sensitive (bool): Whether normalization should preserve case.

    Returns:
        str or None: The normalized file identifier.
    """
    if not isinstance(args_dict, dict):
        return None
    for key in FILE_ARG_KEYS:
        if key in args_dict:
            value = args_dict[key]
            if key == "file_paths" and isinstance(value, list) and value:
                result = os.path.normpath(value[0]).strip()
            else:
                result = os.path.normpath(str(value)).strip()
            if result is not None and not case_sensitive:
                result = result.lower()
            return result
    if "files" in args_dict:
        value = args_dict["files"]
        if isinstance(value, list) and len(value) > 0:
            result = os.path.normpath(value[0]).strip()
            return result.lower() if result and not case_sensitive else result
        elif isinstance(value, dict):
            for k in ("file_path", "filename", "file"):
                if k in value:
                    result = os.path.normpath(value[k]).strip()
                    return result.lower() if result and not case_sensitive else result
            first = next(iter(value.values()), None)
            if first is not None:
                result = os.path.normpath(first).strip()
                return result.lower() if not case_sensitive else result
            return None
    if "file" in args_dict:
        result = os.path.normpath(args_dict["file"]).strip()
        return result.lower() if not case_sensitive else result
    return None

def create_tool_call(raw_tool_call_obj):
    """
    Returns a canonical tool call object.

    For now this is a simple pass-through. Extend as needed.

    Parameters:
        raw_tool_call_obj: The raw input representing a tool call.

    Returns:
        The processed tool call object.
    """
    return raw_tool_call_obj

def backup_file(file_path):
    """
    Creates a backup of the given file by copying it to a new file with a '.last' suffix.

    Args:
        file_path (str): The file to backup.

    Returns:
        str: The backup file path.
    
    Raises:
        Exception: If backup fails.
    """
    backup_path = file_path + ".last"
    try:
        shutil.copy(file_path, backup_path)
    except Exception as e:
        raise Exception(f"Failed to create backup for '{file_path}': {e}")
    return backup_path

def safe_mkdir(dir_path):
    """
    Creates the directory if it does not exist.

    Args:
        dir_path (str): The directory to create.
    
    Raises:
        Exception: If directory creation fails.
    """
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path, exist_ok=True)
        except Exception as e:
            raise Exception(f"Failed to create directory '{dir_path}': {e}")

def run_subprocess_command(cmd, cwd=None, env=None, check=False):
    """
    Executes a subprocess command and returns the CompletedProcess object.

    Args:
        cmd (list): The command (and its arguments).
        cwd (str, optional): Working directory for the command.
        env (dict, optional): Environment variables.
        check (bool, optional): If True, raises an exception for nonzero exit.

    Returns:
        subprocess.CompletedProcess: The result of the command.
    
    Raises:
        Exception: If the command fails when check is True.
    """
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        raise Exception(f"Command '{' '.join(cmd)}' failed: {e.stderr.strip()}") from e

def remove_file(path):
    """
    Removes the file at the given path if it exists.

    Args:
        path (str): The file path.

    Raises:
        Exception: If file removal fails.
    """
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            raise Exception(f"Failed to remove file '{path}': {e}")

def get_current_directory() -> str:
    """
    Logs and returns the current working directory.

    Returns:
        str: The current working directory.
    """
    cwd = os.getcwd()
    logger.debug("Current working directory: " + cwd)
    return cwd

def group_paths(paths: list) -> dict:
    """
    Groups a list of file paths by their immediate parent directory.

    Parameters:
        paths (list): List of file paths as strings.

    Returns:
        dict: A dictionary mapping each parent directory to the list of file paths in that directory.
    """
    groups = {}
    for path in paths:
        parent = os.path.dirname(path)
        groups.setdefault(parent, []).append(path)
    return groups

# NOTE: The following sandbox-related functions have been moved to modules/tools_safety.py:
# • resolve_sandbox_path(file_path: str)
# • resolve_repo_path(path: str)
# • get_sandbox_repo_path(repo_path: str)

# ---------------------------
# Main Demonstration
# ---------------------------
if __name__ == "__main__":
    print("=== Turn Management Demonstration ===")
    try:
        from modules.turns_list import get_turns_list, append_turn, get_active_agent
    except ImportError:
        def get_turns_list(agent_role=None, agent_id=None):
            return []
        def append_turn(agent_role, agent_id, turn):
            pass
        def get_active_agent():
            return "dummy_agent_role", "dummy_agent_id"
    
    class DummyMessage:
        def __init__(self, message_id, role, raw_messages, meta=None):
            self.message_id = message_id
            self.role = role
            self.raw_messages = raw_messages
            self.meta = meta or {}
        def __repr__(self):
            return f"<DummyMessage id={self.message_id} role={self.role} meta={self.meta}>"
    
    assistant = DummyMessage(
        message_id=100,
        role="assistant",
        raw_messages={"content": "Assistant reply."},
        meta={"tool_name": "example_tool", "input_args": {"file_path": "src/file.txt"}, "timestamp": datetime.utcnow().isoformat() + "Z"}
    )
    tool = DummyMessage(
        message_id=101,
        role="tool",
        raw_messages={"content": "Tool response."},
        meta={"timestamp": datetime.utcnow().isoformat() + "Z"}
    )
    
    agent_role, agent_id = get_active_agent()
    global_turns = get_turns_list(agent_role, agent_id)
    if hasattr(global_turns, 'clear'):
        global_turns.clear()
    
    commit_message_pair(assistant, tool)
    
    print("Unified turns:")
    for turn in get_turns_list(agent_role, agent_id):
        print(turn)
    
    print("\n=== Tool Utilities Demonstration ===")
    sample_arg_str = '{"file_path": "Src/MAIN/Java/Example/File.java "}'
    args, norm_key = parse_tool_arguments(sample_arg_str, case_sensitive=False)
    print("Parsed tool arguments:", args)
    print("Normalized key         :", norm_key)
    print("MD5 hash               :", compute_md5_hash(sample_arg_str))
    file_id = get_normalized_file_key(sample_arg_str, case_sensitive=False)
    print("File identifier        :", file_id)
    print("Current directory      :", get_current_directory())
    
    sample_paths = ["src/file1.txt", "src/utils/file2.txt", "docs/readme.md", "src/utils/helpers/file3.txt"]
    grouped = group_paths(sample_paths)
    print("Grouped file paths:")
    print(grouped)
