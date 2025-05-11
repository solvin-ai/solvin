# modules/state_manager.py

"""
Description:
  - Removed defensive try/except blocks in rehydrate_messages, load_agent_state, save_agent_state, and the test message section.
  - Removed legacy fallback for agent identifiers in load_agent_state.
  - Updated config access to use direct indexing (e.g., config["SCRIPT_DIR"] and config.get("REPO_URL")) instead of safe getters.
  - Simplified safe_serialize by removing its try/except fallback; it now recursively processes dicts and lists.
  - Ensured that all persisted messages strictly conform to the new UnifiedTurn structure.
  - NEW: Added create_agent_state() to initialize and store full agent state, as well as update_agent_state_field() for patch updates.
  - NEW: Added load_turns_list() and save_turns_list() to persist and load the conversation turns list from a dedicated file.
  - Also supports deletion of both the full agent state file and the turns_list file.
  
IMPORTANT:
  • All new UnifiedTurn objects are created exclusively via turns_manager.add_unified_turn.
    Do not instantiate UnifiedTurn directly in new code that creates turns.
  • However, for rehydration the persisted state already has full UnifiedTurn data,
    so we directly instantiate UnifiedTurn in this module.
"""

import os
import json
from typing import List, Dict, Any
from marshmallow import Schema, fields, post_load
from shared.logger import logger
logger = logger
from shared.config import config

from modules.turns_utils import get_next_message_id, ensure_unified_turn

# --------------------------------------------------------------------
# Marshmallow Schema for a Persisted UnifiedTurn

class UnifiedTurnSchema(Schema):
    turn_meta = fields.Dict(required=True)
    tool_meta = fields.Dict(required=True)
    messages = fields.Dict(required=True)

    @post_load
    def make_unified_turn(self, data, **kwargs):
        return data

# --------------------------------------------------------------------
# State Directory and Default State Helpers (Private)

def _get_state_dir() -> str:
    """
    Determine the state directory based on SCRIPT_DIR from config.
    """
    script_dir = config["SCRIPT_DIR"]
    state_dir = os.path.join(script_dir, "state")
    os.makedirs(state_dir, exist_ok=True)
    logger.debug("State directory ensured at: %s", os.path.abspath(state_dir))
    return state_dir

def _get_agent_state_file(agent_role: str, agent_id: str) -> str:
    """
    Return the full file path for an agent’s state file.
    The filename is constructed using the repository name (from config) and the provided agent_role
    and agent_id, with double underscores as delimiters:
        <REPO_URL>__<agent_role>__<agent_id>.json
    """
    state_dir = _get_state_dir()
    repo_url = config.get("REPO_URL")
    filename = f"{repo_url}__{agent_role}__{agent_id}.json"
    return os.path.join(state_dir, filename)

def _default_agent_state(agent_role: str, agent_id: str) -> Dict[str, Any]:
    """
    Return the default state structure for an agent.
    This default state includes metadata (repo name, agent role, agent id),
    empty prompts, and an empty list of messages.
    """
    repo_url = config.get("REPO_URL")
    return {
        "repo": repo_url,
        "agent_role": agent_role,
        "agent_id": agent_id,
        "developer_prompt": "",
        "user_prompt": "",
        "messages": []
    }

# --------------------------------------------------------------------
# Serialization Helpers (Private)

def _safe_serialize(obj: Any) -> Any:
    """
    Recursively converts an object into a JSON-serializable structure.
    """
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_safe_serialize(item) for item in obj]
    else:
        return obj

def _serialize_message(msg: Any) -> Dict[str, Any]:
    """
    Converts a UnifiedTurn message into the canonical dictionary form required by our state file.
    If the message is a UnifiedTurn instance, its to_api_message() method is used.
    If msg is already a dictionary (deserialized via Marshmallow), it is returned as-is.
    """
    from modules.unified_turn import UnifiedTurn  # local import for safety.
    if hasattr(msg, "to_api_message"):
        return _safe_serialize(msg.to_api_message())
    elif isinstance(msg, dict):
        return _safe_serialize(msg)
    return msg

# --------------------------------------------------------------------
# Loading State with Marshmallow Rehydration

def load_agent_state(agent_role: str, agent_id: str) -> Dict[str, Any]:
    """
    Load the state for a given agent from its JSON file.
    Validates saved UnifiedTurn messages using UnifiedTurnSchema.
    """
    state_file = _get_agent_state_file(agent_role, agent_id)
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        logger.debug("Loaded state from disk [%s].", state_file)
        messages = state.get("messages", [])
        logger.debug("Number of messages in state: %d", len(messages))
        parsed_messages: List[dict] = []
        schema = UnifiedTurnSchema()
        for index, m in enumerate(messages):
            logger.debug("Processing message %d", index)
            parsed = schema.load(m)
            parsed_messages.append(parsed)
            logger.debug("Message %d parsed successfully.", index)
        state["messages"] = parsed_messages
        return state
    else:
        logger.debug("State file '%s' does not exist. Returning default state.", state_file)
        return _default_agent_state(agent_role, agent_id)

# --------------------------------------------------------------------
# Save Agent State

def save_agent_state(state: Dict[str, Any]):
    """
    Save an agent's state dictionary to disk.
    Before saving, only finalized UnifiedTurn messages are persisted (using Marshmallow dump).
    """
    agent_role = state.get("agent_role")
    agent_id = state.get("agent_id")
    if not agent_role or not agent_id:
        raise ValueError("State dictionary must have 'agent_role' and 'agent_id' keys.")
    state_file = _get_agent_state_file(agent_role, agent_id)

    def is_finalized(msg):
        if isinstance(msg, dict):
            return msg.get("turn_meta", {}).get("finalized", False)
        elif hasattr(msg, "turn_meta"):
            return msg.turn_meta.get("finalized", False)
        return False

    finalized_messages = [msg for msg in state.get("messages", []) if is_finalized(msg)]

    schema = UnifiedTurnSchema(many=True)
    serialized_messages = schema.dump(finalized_messages)
    state["messages"] = serialized_messages
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    logger.debug("State saved successfully to '%s'.", state_file)

# --------------------------------------------------------------------
# Rehydrate Stored Marshmallow Messages into UnifiedTurn Instances

def rehydrate_messages(marshmallow_messages: List[dict]) -> List[Any]:
    """
    Converts a list of persisted UnifiedTurn dictionaries (validated by Marshmallow)
    into UnifiedTurn objects.
    """
    logger.debug("Entering rehydrate_messages with %d messages.", len(marshmallow_messages))
    from modules.unified_turn import UnifiedTurn  # local import to avoid circular dependency
    turns = []
    for msg in marshmallow_messages:
        turn_instance = UnifiedTurn(msg["turn_meta"], msg["tool_meta"], msg["messages"])
        turns.append(turn_instance)
    logger.debug("Completed rehydrate_messages. Total rehydrated messages: %d", len(turns))
    return turns

# --------------------------------------------------------------------
# NEW: Agent State Management Helpers

def create_agent_state(agent_role: str, agent_id: str, developer_prompt: str = "", user_prompt: str = "") -> Dict[str, Any]:
    """
    Create and persist a new agent state file for a given agent_role and agent_id.
    Returns the newly created state dictionary.
    """
    state = _default_agent_state(agent_role, agent_id)
    state["developer_prompt"] = developer_prompt
    state["user_prompt"] = user_prompt
    save_agent_state(state)
    logger.debug("Created new agent state for %s_%s", agent_role, agent_id)
    return state

def update_agent_state_field(agent_role: str, agent_id: str, field: str, value: Any) -> None:
    """
    Loads an agent's state, updates a specific field, and persists the updated state.
    Useful for patching agent metadata.
    """
    state = load_agent_state(agent_role, agent_id)
    state[field] = value
    save_agent_state(state)
    logger.debug("Updated field '%s' for agent %s_%s.", field, agent_role, agent_id)

# --------------------------------------------------------------------
# NEW: Deletion Helpers for Persisted Files

def delete_agent_state(agent_role: str, agent_id: str) -> None:
    """
    Delete the state file associated with a given agent.
    """
    state_file = _get_agent_state_file(agent_role, agent_id)
    if os.path.exists(state_file):
        os.remove(state_file)
        logger.debug("Deleted agent state file: %s", state_file)
    else:
        logger.debug("No agent state file exists at: %s", state_file)

def get_turns_list_file(agent_role: str, agent_id: str) -> str:
    """
    Return the file path for the turns_list file for the agent.
    The filename is constructed similarly to the state file, with a '_turns' suffix.
    """
    state_dir = _get_state_dir()
    repo_url = config.get("REPO_URL")
    filename = f"{repo_url}__{agent_role}__{agent_id}_turns.json"
    return os.path.join(state_dir, filename)

def delete_turns_list(agent_role: str, agent_id: str) -> None:
    """
    Delete the turns_list file (messages) for the specified agent.
    """
    turns_file = get_turns_list_file(agent_role, agent_id)
    if os.path.exists(turns_file):
        os.remove(turns_file)
        logger.debug("Deleted turns list file: %s", turns_file)
    else:
        logger.debug("No turns list file exists at: %s", turns_file)

# --------------------------------------------------------------------
# NEW: Load/Save Helpers for Turns List

def load_turns_list(agent_role: str, agent_id: str) -> List[Any]:
    """
    Load the conversation history (turns list) for the given agent from its dedicated file.
    Returns a list of rehydrated UnifiedTurn instances.
    """
    turns_file = get_turns_list_file(agent_role, agent_id)
    if os.path.exists(turns_file):
        with open(turns_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.debug("Loaded turns list with %d entries from '%s'.", len(data), turns_file)
        return rehydrate_messages(data)
    else:
        logger.debug("No turns list file exists at '%s'. Returning empty list.", turns_file)
        return []

def save_turns_list(turns_list: List[Any], agent_role: str, agent_id: str) -> None:
    """
    Save the provided conversation history (turns list) to its dedicated file for the given agent.
    The turns_list should be a list of UnifiedTurn objects or dictionaries conforming to the UnifiedTurn schema.
    Updated to use Marshmallow for serialization.
    """
    file_path = get_turns_list_file(agent_role, agent_id)
    schema = UnifiedTurnSchema(many=True)
    serialized_turns = schema.dump(turns_list)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(serialized_turns, f, indent=2)
    logger.debug("Turns list saved successfully to '%s'.", file_path)

# --------------------------------------------------------------------
# NEW: Public Helper to List Agent States

def list_agent_states() -> list:
    """
    Scan the state directory for agent state files and return a list of dictionaries,
    each containing keys 'agent_role' and 'agent_id'.
    """
    state_dir = _get_state_dir()
    repo_url = config.get("REPO_URL")
    agents = []
    for filename in os.listdir(state_dir):
        # Exclude non-agent state files (e.g. turns list files)
        if filename.startswith(repo_url) and filename.endswith(".json") and "_turns" not in filename:
            parts = filename.split("__")
            if len(parts) >= 3:
                agent_role = parts[-2]
                agent_id = parts[-1].replace(".json", "")
                agents.append({"agent_role": agent_role, "agent_id": agent_id})
    return agents

# --------------------------------------------------------------------
# For Testing / Demonstration

if __name__ == "__main__":
    import logging
    logger.setLevel(logging.DEBUG)

    # Ensure config values are set.
    test_agent_role = "root"
    test_agent_id = "001"
    logger.info("Loading state for agent role '%s' and id '%s'...", test_agent_role, test_agent_id)
    state = load_agent_state(test_agent_role, test_agent_id)

    print("Current state:")
    print(json.dumps(_safe_serialize(state), indent=2))

    if state.get("messages"):
        logger.debug("State contains %d message(s). Proceeding to rehydrate.", len(state["messages"]))
        unified_turns = rehydrate_messages(state["messages"])
        for ut in unified_turns:
            print("Rehydrated UnifiedTurn (ready for API):")
            print(ut.to_api_message())
    else:
        logger.debug("No messages found in state; rehydrate_messages will not be invoked.")

    # Append a test message to the state.
    test_msg_data = {
        "turn_meta": {
            "turn": 1,
            "finalized": True,
            "total_char_count": 450
        },
        "tool_meta": {
            "tool_name": "git_status",
            "execution_time": 0.2,
            "pending_deletion": False,
            "deleted": False,
            "rejection": None,
            "status": "success",
            "args_hash": "def456",
            "preservation_policy": "until-build",
            "input_args": {
                "query": "Show current git status"
            }
        },
        "messages": {
            "assistant": {
                "meta": {
                    "timestamp": "2023-10-03T15:30:00Z",
                    "original_message_id": 101,
                    "char_count": 150
                },
                "raw": {
                    "role": "assistant",
                    "content": "Here is the output from git status: there are no changes.",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "tool_git_status",
                                "parameters": {}
                            },
                            "timestamp": "2023-10-03T15:30:00Z"
                        }
                    ]
                }
            },
            "tool": {
                "meta": {
                    "timestamp": "2023-10-03T15:30:01Z",
                    "original_message_id": 102,
                    "char_count": 300
                },
                "raw": {
                    "role": "tool",
                    "content": "Git reports a clean working directory."
                }
            }
        }
    }
    schema = UnifiedTurnSchema()
    test_message = schema.load(test_msg_data)
    state["messages"].append(test_message)
    logger.debug("Test message appended.")

    save_agent_state(state)
    print(f"Updated state for agent role '{test_agent_role}' and id '{test_agent_id}' saved.")

    updated_state = load_agent_state(test_agent_role, test_agent_id)
    print("Updated state:")
    print(json.dumps(_safe_serialize(updated_state), indent=2))

    # Demonstrate the new agent state helpers.
    print("\nCreating a new agent state for type 'root' and id '002'.")
    new_state = create_agent_state("root", "002", developer_prompt="Dev prompt here", user_prompt="User prompt here")
    print("New agent state created:")
    print(json.dumps(_safe_serialize(new_state), indent=2))

    print("\nUpdating the developer_prompt for agent 'root_002'.")
    update_agent_state_field("root", "002", "developer_prompt", "Updated dev prompt")
    updated_new_state = load_agent_state("root", "002")
    print("Updated agent state:")
    print(json.dumps(_safe_serialize(updated_new_state), indent=2))

    # Demonstrate deletion of persisted files for a given agent.
    print("\nDeleting persisted state and turns list for agent 'root_002'.")
    delete_agent_state("root", "002")
    delete_turns_list("root", "002")
    print("Deletion complete.")

    # (Optional) Demonstrate load/save for turns list separately.
    print("\nDemonstrating load/save for turns list for agent 'root_001'.")
    # Directly using load_turns_list and save_turns_list functions:
    turns = load_turns_list("root", "001")
    print("Loaded turns list:")
    print(json.dumps(_safe_serialize(turns), indent=2))
    # Append a dummy turn (this is an example; in practice, use your UnifiedTurn objects)
    dummy_turn = test_message  # reusing the test message as a dummy turn
    turns.append(dummy_turn)
    save_turns_list(turns, "root", "001")
    print("Turns list updated and saved.")
