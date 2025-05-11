# modules/tools_registry.py

"""
Updated Tools Registry Module

This module is responsible for discovering, mapping, and preparing tool executor records.
It supports both local execution and Docker-based execution. A global registry is
initialized once at startup via initialize_global_registry() and later retrieved using
get_global_registry().

Note: Tool execution logic (i.e. executing a tool and processing its output) has been moved
to tools_executor.py.
"""

import os
import importlib
import json
import subprocess

from modules.logs import logger
from modules.config import config   # Use config to get centralized paths

# Global registry variable
GLOBAL_TOOLS_REGISTRY = None

def _discover_tools(tools_dir: str = None):
    """
    Discover tool modules from the specified directory.
    Only Python files whose names start with "tool_" and end with ".py" are considered.
    
    Uses config["HOST_TOOLS"] as the base path.
    Returns a list of tool specification dictionaries.
    """
    discovered = []
    
    if tools_dir is None:
        tools_dir = config.get("HOST_TOOLS", os.path.join(config.get("SCRIPT_DIR"), "tools"))
    path_to_tools = tools_dir
    
    if not os.path.exists(path_to_tools):
        logger.warning("Tools directory '%s' does not exist at path '%s'.", tools_dir, path_to_tools)
        return discovered

    package_name = os.path.basename(path_to_tools)
    
    for filename in os.listdir(path_to_tools):
        if not (filename.startswith("tool_") and filename.endswith(".py")):
            continue
        module_name = filename[:-3]  # Remove the '.py' extension.
        import_path = f"{package_name}.{module_name}"
        try:
            mod = importlib.import_module(import_path)
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

                # Record the module name and get_tool function.
                tool_spec["module"] = module_name
                tool_spec["get_tool"] = mod.get_tool

                # Verify that a function specification exists.
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
        except Exception as e:
            logger.exception("Error loading tool from '%s': %s", filename, e)
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

def _execute_tool_via_docker(docker_image: str,
                             host_repos: str,
                             host_tools: str,
                             host_config: str,
                             host_logs: str,
                             repo_name: str,
                             module_name: str,
                             function_name: str,
                             args: dict,
                             turn_id=None) -> str:
    """
    Executes a tool inside a Docker container.

    Constructs and runs a Docker command that mounts necessary host directories into the container,
    sets the working directory, and runs a runner script.
    
    Returns the output string from the tool execution or raises an Exception on error.
    """
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{host_repos}:/app/repos",
        "-v", f"{host_tools}:/app/tools",
        "-v", f"{host_config}:/app/config",
        "-v", f"{host_logs}:/app/logs",
        "-w", f"/app/repos/{repo_name}",
        docker_image,
        "python", "/app/tool_runner.py",
        module_name,
        function_name,
        json.dumps(args)
    ]
    logger.info("[Turn: %s] Running docker command: %s",
                turn_id if turn_id is not None else "N/A", " ".join(docker_cmd))
    proc = subprocess.run(docker_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        error_msg = proc.stderr.strip() or "Unknown error executing tool in container."
        raise Exception(f"Tool command failed with error: {error_msg}")
    return proc.stdout.strip()

def _make_tool_executor(tool, run_in_container: bool):
    """
    Creates a unified executor record for a given tool specification.
    
    The record contains:
      - name, description, and schema (optional JSON schema from tool["function"]["parameters"])
      - preservation policy and tool type (from tool["internal"])
      - executor: a callable that executes the tool (locally or via Docker)
    """
    preservation_policy = tool["internal"].get("preservation_policy")
    tool_type = tool["internal"].get("type", "readonly")
    
    json_schema = None
    if "function" in tool and "parameters" in tool["function"]:
        json_schema = tool["function"]["parameters"]

    func_name = tool["function"].get("name")
    description = tool["function"].get("description", "")
    
    if run_in_container:
        def docker_executor(**kwargs):
            docker_image = docker_executor._docker_params.get("docker_image")
            host_repos = docker_executor._docker_params.get("host_repos")
            host_tools = docker_executor._docker_params.get("host_tools")
            host_config = docker_executor._docker_params.get("host_config")
            host_logs = docker_executor._docker_params.get("host_logs")
            repo_name = docker_executor._docker_params.get("repo_name")
            turn_id = kwargs.pop("turn_id", None)
            return _execute_tool_via_docker(docker_image, host_repos, host_tools,
                                           host_config, host_logs,
                                           repo_name, tool["module"],
                                           func_name, kwargs, turn_id)
        docker_executor._docker_params = {
            "docker_image": config.get("TOOLS_DOCKER_IMAGE", "tools_container"),
            "host_repos": config.get("HOST_REPOS"),
            "host_tools": config.get("HOST_TOOLS"),
            "host_config": config.get("HOST_CONFIG"),
            "host_logs": config.get("HOST_LOGS"),
            "repo_name": config.get("REPO_NAME", scope="service.repos")
        }
        executor_callable = docker_executor
    else:
        # Use a local executor via the wrapper.
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

def _build_tools_registry(tools, run_in_container: bool = True):
    """
    Builds a unified tools registry mapping tool function names to their executor records.
    """
    registry = {}
    for tool in tools:
        if "function" in tool and "module" in tool:
            func_name = tool["function"].get("name")
            if not func_name:
                logger.warning("Tool spec %s is missing a function name.", tool)
                continue
            executor_record = _make_tool_executor(tool, run_in_container)
            registry[func_name] = executor_record
        else:
            logger.warning("Tool spec %s must include both 'function' and 'module' keys.", tool)
    logger.info("Final unified tools registry constructed with keys: %s", list(registry.keys()))
    return registry

def initialize_global_registry(run_in_container: bool = True):
    """
    Initializes and returns a global tools registry.
    This function should be called once at startup.
    """
    global GLOBAL_TOOLS_REGISTRY
    if GLOBAL_TOOLS_REGISTRY is None:
        all_tools = _discover_tools()
        GLOBAL_TOOLS_REGISTRY = _build_tools_registry(all_tools, run_in_container)
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
        registry = initialize_global_registry(run_in_container=False)
        logger.info("Unified tools registry built: %s", registry)
    except Exception as e:
        logger.exception("Failed to initialize global tools registry: %s", e)
