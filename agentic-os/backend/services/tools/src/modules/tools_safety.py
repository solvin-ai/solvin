# modules/tools_safety.py

import os
import re
import inspect
from shared.config import config
from shared.logger import logger

__all__ = [
    "get_repos_dir",
    "get_log_dir",
    "get_repo_path",
    "resolve_repo_path",
    "check_path",
    "mask_output",
    "get_safe_repo_root",
    "resolve_safe_repo_path",
]

def _run_in_container() -> bool:
    """
    Returns True if we should use the in-container mount points
    (CONTAINER_REPOS_DIR / CONTAINER_LOG_DIR) instead of host paths.
    """
    return bool(config.get("RUN_IN_CONTAINER"))

def get_repos_dir() -> str:
    """
    Return the root directory for all repositories.
    If RUN_IN_CONTAINER: use config['CONTAINER_REPOS_DIR'], else config['REPOS_DIR'].
    """
    in_container = _run_in_container()
    key = "CONTAINER_REPOS_DIR" if in_container else "REPOS_DIR"
    logger.debug(
        "get_repos_dir() called from %s, RUN_IN_CONTAINER=%r, reading config['%s']",
        inspect.stack()[1].function,
        in_container,
        key
    )
    c = config.get(key)
    logger.debug("config.get(%r) -> %r", key, c)
    if not c:
        raise RuntimeError(
            f"{key} must be set in config to the "
            f"{'in-container' if in_container else 'host'} repos path."
        )
    real = os.path.abspath(c)
    logger.debug("get_repos_dir() -> %r", real)
    return real

def get_log_dir() -> str:
    """
    Return the root directory for logs/reports.
    If RUN_IN_CONTAINER: use config['CONTAINER_LOG_DIR'], else config['LOG_DIR'].
    """
    in_container = _run_in_container()
    key = "CONTAINER_LOG_DIR" if in_container else "LOG_DIR"
    logger.debug(
        "get_log_dir() called, RUN_IN_CONTAINER=%r, reading config['%s']",
        in_container,
        key
    )
    c = config.get(key)
    logger.debug("config.get(%r) -> %r", key, c)
    if not c:
        raise RuntimeError(
            f"{key} must be set in config to the "
            f"{'in-container' if in_container else 'host'} log path."
        )
    real = os.path.abspath(c)
    logger.debug("get_log_dir() -> %r", real)
    return real

def get_repo_path(repo_name: str) -> str:
    """
    Returns <get_repos_dir()>/<repo_name>.
    """
    return os.path.join(get_repos_dir(), repo_name)

def resolve_repo_path(repo_name: str, file_path: str) -> str:
    """
    Given a repo name and a user-supplied path (absolute or relative),
    return a canonical absolute path inside that repo, or raise on violation.
    """
    repo_root = get_repo_path(repo_name)
    if os.path.isabs(file_path):
        candidate = file_path
    else:
        candidate = os.path.join(repo_root, file_path)
    return check_path(candidate, allowed_root=repo_root)

def check_path(path: str, allowed_root: str = None) -> str:
    """
    Canonicalize via realpath() and assert it lives under:
      • allowed_root (if given), OR
      • get_repos_dir() OR get_log_dir() (if no allowed_root).
    Raises on any violation.
    """
    real = os.path.realpath(path)
    roots = [allowed_root] if allowed_root else [get_repos_dir(), get_log_dir()]

    for root in roots:
        if root:
            rroot = os.path.realpath(root)
            if real == rroot or real.startswith(rroot + os.sep):
                return real

    logger.warning("Access denied: %s is not under %s", real, roots)
    raise RuntimeError(f"Access denied to path: {real}")

def mask_output(output: str) -> str:
    """
    Scrub any absolute references to get_repos_dir() or get_log_dir()
    out of `output`, replacing them with “./repos” and “./logs” respectively.
    Any other absolute-looking path “/foo/bar” becomes “./bar” to avoid leaking info.
    """
    repos = get_repos_dir()
    logs = get_log_dir()

    masked = output.replace(repos, "./repos").replace(logs, "./logs")

    def sub(m):
        p = m.group(0)
        if p.startswith("./"):
            return p
        name = os.path.basename(p.rstrip("/"))
        return "./" + name

    return re.sub(r"/[^\s'\"<>]+", sub, masked)

def get_safe_repo_root() -> str:
    """
    Read REPO_NAME from config, ensure it’s set and that
    <get_repos_dir()>/<REPO_NAME> exists as a directory, then
    return its realpath. Raises RuntimeError otherwise.
    """
    repo_name = config.get("REPO_NAME")
    if not repo_name:
        raise RuntimeError("REPO_NAME is not set in config.")
    repo_root = get_repo_path(repo_name)
    if not os.path.isdir(repo_root):
        raise RuntimeError(f"Repository not found: {repo_root}")
    return os.path.realpath(repo_root)

def resolve_safe_repo_path(file_path: str) -> str:
    """
    Given a user-supplied path (absolute or relative), return its
    canonical realpath under the repo root (as set by REPO_NAME).
    Raises RuntimeError if it points outside that repo.
    """
    repo_root = get_safe_repo_root()
    if os.path.isabs(file_path):
        candidate = file_path
    else:
        candidate = os.path.join(repo_root, file_path)
    return check_path(candidate, allowed_root=repo_root)
