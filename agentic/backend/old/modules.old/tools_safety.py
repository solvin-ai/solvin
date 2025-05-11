# modules/tools_safety.py

"""
This module provides functions to ensure that file system access remains
within a controlled sandbox. It also lets tools work with files and directories
that resolve outside the sandbox if they’re being accessed via known symlinks within it.
"""

import os
import shutil
import re
from pprint import pformat

from modules.config import config  # configuration settings
from modules.logs import logger    # logging setup

__all__ = [
    'set_sandbox_dir',
    'get_sandbox_dir',
    'create_sandbox',
    'initialize_safe_paths',
    'check_path',
    'mask_output',
    'get_sandbox_repo_root',
    'get_sandbox_repos_root',
    'SANDBOX_DIR',
    'SANDBOX_REPOS_ROOT',
    'SANDBOX_REPO_ROOT',
    'resolve_sandbox_path',
    'resolve_repo_path',
    'get_sandbox_repo_path'
]

# Global variables for sandbox management.
SANDBOX_DIR = None         # The root sandbox directory.
SANDBOX_REPOS_ROOT = None  # Directory for repositories (now under DATA_DIR).
SANDBOX_REPO_ROOT = None   # The active repository symlink within the sandbox.

def get_sandbox_repo_root():
    """
    Returns the current sandbox repository root.
    Raises an exception if it isn’t set.
    """
    logger.debug("get_sandbox_repo_root invoked: SANDBOX_REPO_ROOT = %s", SANDBOX_REPO_ROOT)
    if SANDBOX_REPO_ROOT is None:
        config_repo_root = config.get("SANDBOX_REPO_ROOT")
        if config_repo_root:
            logger.warnning("Falling back to config for SANDBOX_REPO_ROOT: %s", config_repo_root)
            return config_repo_root
        raise Exception("SANDBOX_REPO_ROOT is not set! Have you run create_sandbox()?")
    return SANDBOX_REPO_ROOT

def get_sandbox_repos_root():
    """
    Returns the current sandbox repositories root.
    Raises an exception if it isn’t set.
    """
    logger.debug("get_sandbox_repos_root invoked: SANDBOX_REPOS_ROOT = %s", SANDBOX_REPOS_ROOT)
    if SANDBOX_REPOS_ROOT is None:
        config_repos_root = config.get("SANDBOX_REPOS_ROOT")
        if config_repos_root:
            logger.warning("Falling back to config for SANDBOX_REPOS_ROOT: %s", config_repos_root)
            return config_repos_root
        raise Exception("SANDBOX_REPOS_ROOT is not set! Have you run create_sandbox()?")
    return SANDBOX_REPOS_ROOT

def get_sandbox_dir():
    """
    Returns the current sandbox directory.
    Raises an exception if it isn’t set.
    """
    if SANDBOX_DIR is None:
        raise Exception("SANDBOX_DIR is not set! Have you run create_sandbox()?")
    return SANDBOX_DIR

def set_sandbox_dir(path: str) -> None:
    """
    Sets the sandbox directory to the given absolute path, updates the configuration,
    and changes the current working directory to the sandbox.
    """
    global SANDBOX_DIR
    SANDBOX_DIR = os.path.normpath(os.path.abspath(path))
    config["SANDBOX_DIR"] = SANDBOX_DIR
    os.chdir(SANDBOX_DIR)
    #logger.debug("Sandbox directory set to: %s (cwd: %s)", SANDBOX_DIR, os.getcwd())

def create_sandbox(sandbox_path: str, repo_path: str, logs_path: str, thoughts_path: str) -> None:
    """
    Creates a new sandbox directory and sets up its structure by creating directories and symbolic links:
      • A 'repos' directory (created under DATA_DIR) containing a symlink to the real repository.
      • A symlink for the logs directory.
      • A symlink for the thoughts directory.
      • A symlink for the requests directory (derived from DATA_DIR in config).
      • Copies the "modules" and "tools" source code directories (without symlinks) from SCRIPT_DIR.
    
    Any existing sandbox at sandbox_path is removed.
    """
    sandbox_path = os.path.normpath(os.path.abspath(sandbox_path))
    if os.path.exists(sandbox_path):
        shutil.rmtree(sandbox_path)
    os.makedirs(sandbox_path, exist_ok=True)

    # Create the "repos" directory under DATA_DIR instead of sandbox_path.
    data_dir = config.get("DATA_DIR")
    if not data_dir:
        raise Exception("DATA_DIR must be set in the configuration.")
    data_dir = os.path.normpath(os.path.abspath(data_dir))
    global SANDBOX_REPOS_ROOT
    SANDBOX_REPOS_ROOT = os.path.join(data_dir, "repos")
    os.makedirs(SANDBOX_REPOS_ROOT, exist_ok=True)

    # Create the repository symlink.
    normalized_repo_path = os.path.normpath(os.path.abspath(repo_path))
    repo_name = os.path.basename(normalized_repo_path)
    repo_link = os.path.join(SANDBOX_REPOS_ROOT, repo_name)
    if os.path.normpath(os.path.abspath(repo_link)) != normalized_repo_path:
        if os.path.lexists(repo_link):
            os.remove(repo_link)
        os.symlink(normalized_repo_path, repo_link)
    else:
        logger.debug("Skipping symlink creation: repo_path and repo_link are identical (%s)", normalized_repo_path)

    # Create the logs symlink.
    logs_link = os.path.join(sandbox_path, "logs")
    os.symlink(logs_path, logs_link)

    # Ensure the target directory for thoughts exists before creating the symlink.
    if not os.path.exists(thoughts_path):
        os.makedirs(thoughts_path, exist_ok=True)
    # Create the thoughts symlink.
    thoughts_link = os.path.join(sandbox_path, "thoughts")
    os.symlink(thoughts_path, thoughts_link)

    # Create the requests symlink from DATA_DIR.
    data_dir_config = config.get("DATA_DIR")
    if not data_dir_config:
        raise Exception("DATA_DIR must be set in the configuration.")
    requests_src = os.path.join(os.path.normpath(os.path.abspath(data_dir_config)), "requests")
    requests_link = os.path.join(sandbox_path, "requests")
    os.symlink(requests_src, requests_link)

    # Set the sandbox directory.
    set_sandbox_dir(sandbox_path)

    global SANDBOX_REPO_ROOT
    SANDBOX_REPO_ROOT = repo_link

    # Update configuration with the new paths.
    config["SANDBOX_REPOS_ROOT"] = SANDBOX_REPOS_ROOT
    config["SANDBOX_REPO_ROOT"] = SANDBOX_REPO_ROOT

    # Copy the source code directories "modules" and "tools" into the sandbox without using symlinks.
    script_dir = config.get("SCRIPT_DIR")
    if not script_dir:
        raise Exception("SCRIPT_DIR must be set in the configuration.")
    source_modules = os.path.join(script_dir, "modules")
    source_tools = os.path.join(script_dir, "tools")
    dest_modules = os.path.join(sandbox_path, "modules")
    dest_tools = os.path.join(sandbox_path, "tools")
    if os.path.exists(source_modules):
        shutil.copytree(source_modules, dest_modules, symlinks=False)
    if os.path.exists(source_tools):
        shutil.copytree(source_tools, dest_tools, symlinks=False)

def initialize_safe_paths():
    """
    Initializes safe paths by setting the sandbox directory to "sandbox" under SCRIPT_DIR.
    """
    script_dir = config.get("SCRIPT_DIR")
    if not script_dir:
        raise Exception("SCRIPT_DIR must be set in the configuration.")
    sandbox_path = os.path.join(os.path.normpath(os.path.abspath(script_dir)), "sandbox")
    logger.debug("Initializing safe paths: SCRIPT_DIR=%s, sandbox_path=%s, cwd=%s", script_dir, sandbox_path, os.getcwd())
    set_sandbox_dir(sandbox_path)

def check_path(path: str, allow_root: bool = False, symlink_source: str = None) -> str:
    """
    Verifies that the given 'path' resides inside the sandbox (SANDBOX_DIR).

    When a symlink_source is provided, its absolute (non-resolved) path is used for the security check.
    This allows access to targets outside the sandbox if they’re being reached via a symlink inside it.

    If the fully resolved path lies outside the sandbox, an attempt is made to remap it via known
    symlink mappings under SANDBOX_REPOS_ROOT.

    Args:
        path (str): The candidate file or directory.
        allow_root (bool): If True, the check is bypassed.
        symlink_source (str): The original symlink path (if applicable).

    Returns:
        str: The normalized absolute path (possibly remapped into the sandbox).

    Raises:
        Exception: If the effective path is determined to be outside the sandbox.
    """
    if symlink_source is None and os.path.islink(path):
        symlink_source = path

    if symlink_source is not None:
        effective = os.path.normpath(os.path.abspath(symlink_source))
    else:
        effective = os.path.normpath(os.path.realpath(path))

    if allow_root:
        resolved = os.path.normpath(os.path.realpath(path))
        return resolved

    safe_root = os.path.normpath(os.path.realpath(SANDBOX_DIR))

    if effective == safe_root or effective.startswith(safe_root + os.sep):
        ret_path = os.path.normpath(os.path.realpath(path))
        return ret_path
    else:
        mapped = None
        if SANDBOX_REPOS_ROOT and os.path.exists(SANDBOX_REPOS_ROOT):
            for entry in os.listdir(SANDBOX_REPOS_ROOT):
                candidate = os.path.join(SANDBOX_REPOS_ROOT, entry)
                if os.path.islink(candidate):
                    try:
                        link_target = os.readlink(candidate)
                    except OSError:
                        logger.error("Failed os.readlink on candidate '%s'", candidate)
                        continue
                    if not os.path.isabs(link_target):
                        target_absolute = os.path.normpath(os.path.abspath(os.path.join(os.path.dirname(candidate), link_target)))
                    else:
                        target_absolute = os.path.normpath(link_target)
                    try:
                        common = os.path.commonpath([effective, target_absolute])
                    except Exception as e:
                        logger.error("os.path.commonpath exception for effective='%s', target_absolute='%s': %s", effective, target_absolute, e)
                        common = ""
                    if common == target_absolute:
                        relative_subpath = os.path.relpath(effective, target_absolute)
                        mapped = os.path.normpath(os.path.join(candidate, relative_subpath))
                        break

        if mapped is not None and (mapped == safe_root or mapped.startswith(safe_root + os.sep)):
            return mapped
        else:
            rel_path = os.path.relpath(effective, safe_root)
            error_msg = f"Access denied: '{os.path.join('.', rel_path)}' is outside the allowed directory '.'"
            logger.warning(error_msg)
            raise Exception(error_msg)

def mask_output(output: str) -> str:
    """
    Replaces absolute paths in the output with relative paths so that sensitive
    directories (like the sandbox) are not exposed.

    Args:
        output (str): The string potentially containing absolute paths.

    Returns:
        str: The masked output.
    """
    if SANDBOX_DIR is None:
        if config.get("SCRIPT_DIR") is not None:
            initialize_safe_paths()
        else:
            raise Exception("Sandbox directory not set and SCRIPT_DIR missing from configuration. Offending object:\n" + pformat(SANDBOX_DIR))
    masked = output.replace(SANDBOX_DIR, ".")

    def replace_absolute(match):
        abs_path = match.group(0)
        if abs_path.startswith(SANDBOX_DIR):
            return abs_path.replace(SANDBOX_DIR, ".")
        else:
            return os.path.join('.', os.path.basename(abs_path))

    masked = re.sub(r'/(?:(?!\s)[^\s\'"]+)', replace_absolute, masked)
    return masked

# ─── SANDBOX PATH RESOLUTION FUNCTIONS ──────────────────────────────

def resolve_sandbox_path(file_path: str) -> str:
    """
    Resolves the given file_path within the sandbox.
    
    • If the path is relative, it is joined with SANDBOX_REPOS_ROOT.
    • If the path is a symlink, check_path is invoked with the symlink as source.
    • Logs the resolution process.
    """
    if not os.path.isabs(file_path):
        file_path = os.path.join(SANDBOX_REPOS_ROOT, file_path)
    if os.path.islink(file_path):
        safe_path = check_path(file_path, symlink_source=file_path)
    else:
        safe_path = check_path(file_path)
    #logger.debug("Resolved sandbox path for '%s' to '%s'", file_path, safe_path)
    return safe_path

def resolve_repo_path(path: str) -> str:
    """
    Resolves a given path relative to the repository sandbox.
    
    • Returns the normalized absolute path.
    • If the path is relative, it is joined with SANDBOX_REPOS_ROOT.
    
    Raises:
        Exception: If SANDBOX_REPOS_ROOT is not set.
    """
    if os.path.isabs(path):
        return os.path.normpath(path)
    else:
        if SANDBOX_REPOS_ROOT is None:
            raise Exception("SANDBOX_REPOS_ROOT is not set! Sandbox environment required.")
        return os.path.normpath(os.path.join(SANDBOX_REPOS_ROOT, path))

def get_sandbox_repo_path(repo_path: str) -> str:
    """
    Remaps a real repository absolute path to the corresponding sandbox path.
    
    If repo_path starts with the real repository root (from config["REPO_ROOT"]),
    its prefix is replaced with SANDBOX_REPOS_ROOT.
    
    Returns:
        The sandbox equivalent path, or the original path if no mapping applies.
    """
    try:
        from modules.config import config
        repo_real_root = config.get("REPO_ROOT")
    except Exception as e:
        logger.warning("[get_sandbox_repo_path] Could not load config: %s", e)
        repo_real_root = None

    if repo_real_root and repo_path.startswith(repo_real_root):
        relative_part = os.path.relpath(repo_path, repo_real_root)
        mapped_path = os.path.join(SANDBOX_REPOS_ROOT, relative_part)
        return mapped_path
    else:
        return repo_path
