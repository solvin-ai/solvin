# modules/tools_registry.py

"""
Updated Tools Registry Module

This module is responsible for discovering, mapping, and preparing tool executor records.
It supports only local execution, assuming the service and tools both run in the same
Docker container. A global registry is initialized once at startup via 
initialize_global_registry() and later retrieved using get_global_registry().
"""

import os
import importlib
import importlib.util
import json

from shared.logger import logger
from shared.config import config   # Use config to get centralized paths

# Global registry variable
GLOBAL_TOOLS_REGISTRY = None

def _get_tools_dir():
    """
    Determines the tools directory path as 'tools' subdir
    at the root of the service, one level above this script.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))    # modules dir
    service_root = os.path.dirname(script_dir)                 # service root
    tools_dir = os.path.join(service_root, "tools")            # ../tools
    logger.debug(f"tools_dir %s", tools_dir)
    return tools_dir

def _discover_tools(tools_dir: str = None):
    """
    Discover tool modules from the specified directory.
    Only Python files whose names start with "tool_" and end with ".py" are considered.
    Returns a list of tool specification dictionaries.
    """
    discovered = []
    if tools_dir is None:
        tools_dir = _get_tools_dir()
    path_to_tools = tools_dir

    if not os.path.exists(path_to_tools):
        logger.warning("Tools directory '%s' does not exist at path '%s'.", tools_dir, path_to_tools)
        return discovered

    for filename in os.listdir(path_to_tools):
        if not (filename.startswith("tool_") and filename.endswith(".py")):
            continue
        module_name = filename[:-3]
        try:
            import_path = f"tools.{module_name}"
            mod = importlib.import_module(import_path)
        except ImportError:
            full_path = os.path.join(path_to_tools, filename)
            spec = importlib.util.spec_from_file_location(module_name, full_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            else:
                logger.error("Could not import tool module '%s'", filename)
                continue

        if hasattr(mod, "get_tool"):
            tool_spec = mod.get_tool()
            if not isinstance(tool_spec, dict):
                logger.warning("Tool from module '%s' is not a dictionary.", filename)
                continue
            if "internal" not in tool_spec or not isinstance(tool_spec["internal"], dict):
                logger.warning("Tool spec in module '%s' is missing an 'internal' key or it is not a dict.", filename)
                continue
            internal = tool_spec["internal"]
            if "type" not in internal or "preservation_policy" not in internal:
                logger.warning("Tool spec in module '%s' must have both 'type' and 'preservation_policy' under 'internal'.", filename)
                continue

            tool_spec["module"] = module_name
            tool_spec["get_tool"] = mod.get_tool

            if "function" in tool_spec:
                func_name = tool_spec["function"].get("name")
                if func_name and hasattr(mod, func_name):
                    tool_spec["run"] = getattr(mod, func_name)
                    discovered.append(tool_spec)
                    logger.debug("Loaded tool '%s' from '%s'.", func_name, filename)
                else:
                    logger.warning("Tool spec in module '%s' is missing a valid function name.", filename)
            else:
                logger.warning("Tool spec in module '%s' is missing the 'function' key.", filename)
        else:
            logger.warning("Module '%s' does not define get_tool().", filename)
    return discovered

def _make_local_tool_wrapper(get_tool_func, run_func):
    """
    Creates a wrapper for local tool execution.
    When called without any arguments and with _execution=False, returns the tool spec.
    Otherwise, it executes the run function.
    """
    def wrapper(*args, _execution=False, **kwargs):
        if not _execution and not args and not kwargs:
            return get_tool_func()
        else:
            return run_func(*args, **kwargs)
    return wrapper

def _make_tool_executor(tool):
    """
    Creates a unified executor record for a given tool specification.
    The record contains:
      - name, description, and schema (optional JSON schema from tool["function"]["parameters"])
      - preservation policy and tool type (from tool["internal"])
      - executor: a callable that executes the tool (local)
    """
    preservation_policy = tool["internal"].get("preservation_policy")
    tool_type = tool["internal"].get("type", "readonly")

    json_schema = None
    if "function" in tool and "parameters" in tool["function"]:
        json_schema = tool["function"]["parameters"]

    func_name = tool["function"].get("name")
    description = tool["function"].get("description", "")

    local_wrapper = _make_local_tool_wrapper(tool["get_tool"], tool["run"])
    executor_callable = local_wrapper

    return {
        "name": func_name,
        "description": description,
        "schema": json_schema,
        "preservation_policy": preservation_policy,
        "type": tool_type,
        "executor": executor_callable
    }

def _build_tools_registry(tools):
    """
    Builds a unified tools registry mapping tool function names (without 'tool_' prefix)
    to their executor records.
    """
    registry = {}
    for tool in tools:
        if "function" in tool and "module" in tool:
            func_name = tool["function"].get("name")
            if not func_name:
                logger.warning("Tool spec %s is missing a function name.", tool)
                continue

            # strip off leading "tool_" prefix
            if func_name.startswith("tool_"):
                key = func_name[len("tool_"):]
            else:
                key = func_name

            executor_record = _make_tool_executor(tool)
            # override the internal name to match the stripped key
            executor_record["name"] = key
            registry[key] = executor_record
        else:
            logger.warning("Tool spec %s must include both 'function' and 'module' keys.", tool)
    logger.info("Final unified tools registry constructed with keys: %s", list(registry.keys()))
    return registry

def initialize_global_registry():
    """
    Initializes and returns a global tools registry.
    This function should be called once at startup.
    """
    global GLOBAL_TOOLS_REGISTRY
    if GLOBAL_TOOLS_REGISTRY is None:
        all_tools = _discover_tools()
        GLOBAL_TOOLS_REGISTRY = _build_tools_registry(all_tools)
        logger.info("Global tools registry initialized with keys: %s", list(GLOBAL_TOOLS_REGISTRY.keys()))
    return GLOBAL_TOOLS_REGISTRY

def get_global_registry():
    """
    Returns the global tools registry. Raises an error if it has not been initialized.
    """
    if GLOBAL_TOOLS_REGISTRY is None:
        raise ValueError("Global tools registry not initialized. Call initialize_global_registry() first.")
    return GLOBAL_TOOLS_REGISTRY

if __name__ == "__main__":
    # Test global registry initialization.
    try:
        registry = initialize_global_registry()
        logger.info("Unified tools registry built: %s", registry)
    except Exception as e:
        logger.exception("Failed to initialize global tools registry: %s", e)