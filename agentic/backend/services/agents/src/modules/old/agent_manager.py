# modules/agent_manager.py

"""
Agent Manager Module

This module manages agent configuration and selection.
Static agent configuration (“the registry”) is fetched via the API endpoint
and stored in the global _static_registry.
For each agent, the registry contains:
    • "agent_role"
    • "developer_prompt"     (sourced from "default_developer_prompt")
    • "allowed_tools"        (normalized)

Dynamic agent instances (each with a unique agent_id) are tracked in memory via _running_state.
There are two related concepts:
  – Live agents: All agents that have been activated (stored in _running_state).
  – Running agent: The single agent that is currently assigned for processing.
The only persistent state in our system is the turns_list (message history), which is now handled
via state_manager/turns_list.

This updated module provides methods to:
   • Fetch the static configuration registry.
   • Manage dynamic (live) agent states.
   • Validate allowed tools.
   • Initialize the entire system via init_agent_manager (only once).
   • Destroy an agent by removing its dynamic state and delegating turns deletion to turns_list.
"""

import os
import json
import requests
from shared.logger import logger
logger = logger

from shared.config import config
AGENT_MANAGER_API_URL = config.get("AGENT_MANAGER_API_URL", os.environ.get("AGENT_MANAGER_API_URL", "localhost:3000"))

# API endpoints for the static configuration (the registry) and tasks.
REGISTRY_API_BASE = f"http://{AGENT_MANAGER_API_URL}/api/agent-types"
TASKS_API_BASE     = f"http://{AGENT_MANAGER_API_URL}/api/tasks"


def _substitute_expressions(text):
    """
    Replaces placeholders in the form {KEY} with corresponding environment variable values.
    """
    for key, value in os.environ.items():
        placeholder = "{" + key + "}"
        text = text.replace(placeholder, value)
    return text


# Global in-memory storage for the static configuration registry.
# _static_registry maps agent_role -> {
#     "agent_role": <agent_role>,
#     "developer_prompt": <default_developer_prompt>,
#     "allowed_tools": <normalized tools list>
# }
_static_registry = {}


def _fetch_registry():
    """
    Loads static configuration for all agents from REGISTRY_API_BASE.
    Expects the API to return agents either under "agentTypes", "agents",
    or as a direct list.
    Populates the global _static_registry.
    """
    global _static_registry
    try:
        logger.debug("Loading static registry from API: %s", REGISTRY_API_BASE)
        response = requests.get(REGISTRY_API_BASE)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                agents = data
            elif data.get("agentTypes") is not None:
                agents = data.get("agentTypes")
            elif data.get("agents") is not None:
                agents = data.get("agents")
            else:
                agents = []
            registry = {}
            for agent in agents:
                atype = agent.get("agent_role")
                if not atype:
                    continue
                # Get the default developer prompt from "default_developer_prompt"
                developer_prompt = agent.get("default_developer_prompt", "")
                allowed_tools_str = agent.get("allowed_tools", "[]")
                try:
                    tools = json.loads(allowed_tools_str)
                except Exception as e:
                    logger.error("Error parsing allowed_tools for agent_role '%s': %s", atype, e)
                    tools = []
                normalized_tools = []
                for tool in tools:
                    norm = _normalize_tool_name(tool)
                    if not norm.startswith("tool_"):
                        norm = "tool_" + norm
                    normalized_tools.append(norm)
                registry[atype] = {
                    "agent_role": atype,
                    "developer_prompt": developer_prompt,
                    "allowed_tools": normalized_tools
                }
            _static_registry = registry
            logger.debug("Static registry fetched: %s", _static_registry)
        else:
            logger.error("Failed to load static registry. HTTP status: %s", response.status_code)
    except Exception as e:
        logger.error("Exception loading static registry: %s", e)


def get_agent_config(agent_role):
    """
    Retrieves the static configuration for the specified agent_role from _static_registry.
    Returns a dict with keys "agent_role", "developer_prompt", and "allowed_tools"
    or an empty dict if not found.
    """
    global _static_registry
    if not _static_registry:
        _fetch_registry()
    config_data = _static_registry.get(agent_role, {})
    logger.debug("Registry for agent_role '%s': %s", agent_role, config_data)
    return config_data


def get_agent_tools(agent_role):
    """
    Returns the allowed tools for the given agent_role.
    """
    config_data = get_agent_config(agent_role)
    tools = config_data.get("allowed_tools", [])
    logger.debug("Allowed tools for '%s' from registry: %s", agent_role, tools)
    return tools


def get_agent_prompts(agent_role):
    """
    Returns a tuple (developer_prompt, user_prompt) for the specified agent_role.
    • developer_prompt is sourced from the static registry.
    • user_prompt is fetched from the TASKS_API_BASE endpoint using TASK_NAME from config.
    Both prompts have environment variable substitutions applied.
    """
    config_data = get_agent_config(agent_role)
    developer_prompt = config_data.get("developer_prompt", "")
    if not developer_prompt:
        logger.error("No developer prompt found in registry for agent_role '%s'", agent_role)
    try:
        from shared.config import config
        TASK_NAME = config.get("TASK_NAME")
        if not TASK_NAME:
            raise ValueError("TASK_NAME is not defined in configuration.")
        url = f"{TASKS_API_BASE}?task_name={TASK_NAME}"
        logger.debug("Fetching task prompt for agent_role '%s' using TASK_NAME '%s': %s",
                     agent_role, TASK_NAME, url)
        response = requests.get(url)
        if response.status_code == 200:
            user_prompt = response.json().get("task", {}).get("task_prompt", "")
        else:
            logger.error("Failed to fetch task prompt. HTTP status: %s", response.status_code)
            user_prompt = ""
    except Exception as e:
        logger.error("Exception fetching task prompt: %s", e)
        user_prompt = ""
    developer_prompt = _substitute_expressions(developer_prompt)
    user_prompt = _substitute_expressions(user_prompt)
    from shared.config import config
    config.set("LLM_USER_PROMPT", user_prompt)
    return developer_prompt, user_prompt


# ------------------ Dynamic Agent State Management (Live Agents) ------------------

# In-memory store for dynamic agent states.
# Mapping: (agent_role, agent_id) -> state
_running_state = {}
_running_agent = None  # The currently running (selected) agent as a tuple (agent_role, agent_id)
_current_state = None


def _init_running_agents_states():
    """
    Initializes the in-memory _running_state by reading from disk exactly once at boot.
    After initialization, all dynamic state operations use the in-memory _running_state.
    """
    global _running_state
    try:
        from modules.state_manager import list_agent_states
        agents = list_agent_states()
        for agent in agents:
            key = (agent.get("agent_role"), agent.get("agent_id"))
            _running_state[key] = agent
        logger.debug("Initialized running_state (live agents) from disk: %s", _running_state)
    except Exception as e:
        logger.error("Failed to initialize running_state from disk: %s", e)


def _get_local_state():
    """
    Retrieves the list of dynamic agent states from the in-memory _running_state.
    Does NOT read from the filesystem after boot.
    """
    return list(_running_state.values())


def _persist_running_state():
    """
    Records the list of active agents currently live.
    Here we simply log the list of live agents (agent_role, agent_id).
    """
    live_agents = list(_running_state.keys())
    logger.debug("Live agents (agent_role, agent_id): %s", live_agents)


def _validate_allowed_tools_for_agent_role(agent_role, tools_dir=None):
    """
    Validates that allowed tools (from the registry for a given agent_role)
    are present in the tools directory.
    Returns True if validation passes, False otherwise.
    """
    logger.debug("Validating allowed tools for agent_role '%s'", agent_role)
    raw_allowed = get_agent_tools(agent_role)
    allowed = set(raw_allowed)
    possible = set(_get_all_possible_tools(tools_dir))
    missing_tools = allowed - possible
    if missing_tools:
        logger.error("Validation Error: Missing tools for agent_role '%s': %s",
                     agent_role, list(missing_tools))
        return False
    logger.debug("All allowed tools for agent_role '%s' are present.", agent_role)
    return True


def create_new_agent(agent_role):
    """
    Creates a new dynamic agent for the specified agent_role:
      • Validates the allowed tools.
      • Determines a sequential agent_id.
      • Constructs an initial state via state_manager and records it in _running_state.
      • Persists the new agent info (via logging).
      • Returns the new agent_id.
    """
    # Validate allowed tools before creating agent.
    if not _validate_allowed_tools_for_agent_role(agent_role):
        raise ValueError(f"Allowed tools validation failed for agent role '{agent_role}'. "
                         "Check the registry and tools directory.")

    logger.debug("Creating a new dynamic agent for agent_role '%s'", agent_role)
    local_state = _get_local_state()
    existing_ids = []
    for agent in local_state:
        if agent.get("agent_role") == agent_role:
            agent_id = agent.get("agent_id")
            if agent_id is not None:
                try:
                    existing_ids.append(int(agent_id))
                except ValueError:
                    logger.warning("Non-numeric agent-id '%s' encountered for '%s'; skipping.",
                                   agent_id, agent_role)
    new_id_int = max(existing_ids) + 1 if existing_ids else 1
    new_agent_id = str(new_id_int).zfill(3)
    logger.debug("Determined new agent_id '%s' for agent_role '%s'", new_agent_id, agent_role)
    try:
        from modules.state_manager import create_agent_state
        new_state = create_agent_state(agent_role, new_agent_id)
        logger.debug("Created new dynamic agent state for '%s_%s'.", agent_role, new_agent_id)
        _running_state[(agent_role, new_agent_id)] = new_state
        _persist_running_state()
    except Exception as e:
        logger.error("Failed to create dynamic agent state for '%s_%s': %s",
                     agent_role, new_agent_id, e)
        raise e
    return new_agent_id


def _ensure_default_agent():
    """
    Ensures there is at least one dynamic agent.
    If none exists for DEFAULT_AGENT_TYPE (from config, e.g., "root"), auto-creates one.
    Then selects (by lowest agent_id) and sets it as the running agent.
    Returns a tuple: (agent_role, agent_id) for the running agent.
    """
    local_state = _get_local_state()
    from shared.config import config
    default_agent_role = config.get("DEFAULT_AGENT_TYPE", "root")
    default_agents = [a for a in local_state if a.get("agent_role") == default_agent_role]
    if not default_agents:
        logger.debug("No dynamic state found for DEFAULT_AGENT_TYPE '%s'. Auto-creating one.", default_agent_role)
        new_agent_id = create_new_agent(default_agent_role)
        default_agents = [{"agent_role": default_agent_role, "agent_id": new_agent_id}]
        local_state = _get_local_state()
    chosen = sorted(default_agents, key=lambda a: int(a.get("agent_id", "0")))[0]
    switch_running_agent(chosen["agent_role"], chosen["agent_id"])
    logger.debug("Default dynamic (running) agent set to: (%s, %s)", chosen["agent_role"], chosen["agent_id"])
    return (chosen["agent_role"], chosen["agent_id"])


def get_running_agent():
    """
    Returns the currently running dynamic agent as a tuple: (agent_role, agent_id).
    """
    return _running_agent


def switch_running_agent(agent_role, agent_id):
    """
    Switches the running agent to the specified (agent_role, agent_id).
    Loads the agent's state from _running_state.
    Returns the agent's state.
    """
    global _running_agent, _current_state
    logger.debug("Switching running agent to '%s_%s'", agent_role, agent_id)
    _running_agent = (agent_role, agent_id)
    if _running_agent in _running_state:
        _current_state = _running_state[_running_agent]
        logger.debug("State for running agent '%s_%s' loaded from in-memory state.", agent_role, agent_id)
    else:
        logger.error("Dynamic state for '%s_%s' not found in memory.", agent_role, agent_id)
        raise KeyError(f"Dynamic state for {agent_role}_{agent_id} not found in memory.")
    return _current_state


def list_live_agents(agent_role=None):
    """
    Returns a list of live (active) agents from the in-memory _running_state.
    Each agent is returned as a dictionary with keys "agent_role" and "agent_id".
    If agent_role is provided, only agents matching that type are returned.
    """
    agents = [{"agent_role": key[0], "agent_id": key[1]} for key in _running_state.keys()]
    if agent_role:
        agents = [agent for agent in agents if agent["agent_role"] == agent_role]
    return agents


def load_agent_state(agent_role, agent_id):
    """
    Retrieves the dynamic state for the specified agent from _running_state.
    Raises KeyError if not found.
    """
    key = (agent_role, agent_id)
    if key in _running_state:
        logger.debug("Loaded dynamic state for agent '%s_%s' from memory.", agent_role, agent_id)
        return _running_state[key]
    else:
        logger.error("Dynamic state for agent '%s_%s' not found in memory.", agent_role, agent_id)
        raise KeyError(f"Dynamic state for {agent_role}_{agent_id} not found in memory.")


# ------------------ Tool Names Normalization and Validation ------------------

def _normalize_tool_name(tool):
    """
    Normalizes a tool name by converting it to lowercase and replacing spaces with underscores.
    """
    normalized = tool.lower().replace(" ", "_")
    logger.debug("Normalized tool name '%s' to '%s'", tool, normalized)
    return normalized


def _get_all_possible_tools(tools_dir=None):
    """
    Iterates through the specified (or default) tools directory and returns a list of possible tool names.
    """
    logger.debug("Getting all possible tools. tools_dir='%s'", tools_dir)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if tools_dir is None:
        tools_dir = os.path.join(BASE_DIR, "tools")
    if not os.path.isdir(tools_dir):
        logger.debug("Tools directory '%s' not found.", tools_dir)
        return []
    possible = []
    for filename in os.listdir(tools_dir):
        if filename.startswith("tool_") and filename.endswith(".py"):
            tool_name = filename[:-3]
            normalized_tool = _normalize_tool_name(tool_name)
            possible.append(normalized_tool)
    logger.debug("Possible tools found: %s", possible)
    return possible


def destroy_agent(agent_role, agent_id):
    """
    Destroys a dynamic agent by:
      • Removing it from _running_state.
      • Deleting its persisted state and conversation history.
         The persisted state is deleted via state_manager.delete_agent_state.
         The conversation history (turns list) is deleted via turns_list.delete_turns_list.
    Does not notify any API.
    """
    global _running_state
    key = (agent_role, agent_id)
    if key not in _running_state:
        logger.error("Dynamic agent '%s_%s' not found in running_state.", agent_role, agent_id)
        return False
    try:
        from modules.state_manager import delete_agent_state
        delete_agent_state(agent_role, agent_id)
        logger.debug("Deleted persisted dynamic state for agent '%s_%s'.", agent_role, agent_id)
    except Exception as e:
        logger.error("Error deleting persisted dynamic state for agent '%s_%s': %s",
                     agent_role, agent_id, e)
    try:
        from modules.turns_list import delete_turns_list
        delete_turns_list(agent_role, agent_id)
        logger.debug("Deleted turns list for agent '%s_%s'.", agent_role, agent_id)
    except Exception as e:
        logger.error("Error deleting turns list for agent '%s_%s': %s",
                     agent_role, agent_id, e)
    del _running_state[key]
    logger.debug("Removed dynamic agent '%s_%s' from running_state.", agent_role, agent_id)
    _persist_running_state()
    return True


# ------------------ Exposing Live Agents ------------------

def get_live_agents_for_export():
    """
    Returns a dynamic list of live agents based on _running_state.
    Each agent is returned as a dict with keys "agent_role" and "agent_id".
    """
    return list_live_agents()


def __getattr__(name):
    """
    Provides dynamic attributes for the module.
    Exposes live_agents as a dynamic property.
    """
    if name == "live_agents":
        return list_live_agents()
    raise AttributeError(f"module {__name__} has no attribute {name}")


# ------------------ Generic Initialization for Agent Manager ------------------

_initialized = False  # Module-level flag to ensure initialization runs only once

def init_agent_manager():
    """
    Generic initialization method for Agent Manager.
    Loads the static registry, dynamic agent states from disk,
    and ensures there is at least one (default) dynamic agent running.
    This function runs only once, regardless of how many times it is called.
    """
    global _initialized
    if _initialized:
        logger.debug("Agent Manager already initialized. Skipping initialization.")
        return
    _fetch_registry()
    _init_running_agents_states()
    _ensure_default_agent()
    _initialized = True
    logger.debug("Agent Manager initialization complete.")


# ------------------ Main Testing Block ------------------

if __name__ == "__main__":
    init_agent_manager()
    logger.debug("Running Agent Manager tests")
    print("=== Agent Manager Tests ===")
    print("Static registry for 'root':", get_agent_config("root"))
    print("Allowed tools for 'root':", get_agent_tools("root"))
    print("Dynamic state (live agents):", _get_local_state())
    default_agent = get_running_agent()
    print("Default dynamic (running) agent set:", default_agent)
    print("Live agents (all dynamic agents):", list_live_agents())
    print("Live agents filtered by 'root':", list_live_agents("root"))
    # Test allowed tools validation
    valid = _validate_allowed_tools_for_agent_role("root")
    print("Are allowed tools valid for 'root'? ->", valid)
    # Test switching running agent if possible (uncomment below for testing)
    # new_agent = create_new_agent("root")
    # switch_running_agent("root", new_agent)
    # print("Switched running agent:", get_running_agent())
