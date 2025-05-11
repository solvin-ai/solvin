# admission/__init__.py

import pkgutil, importlib, sys
from typing import Callable, Dict, Any
from shared.logger import logger

TASK_REGISTRY = {}

def admission_task(name: str):
    def decorator(fn: Callable[[str, Dict[str, Any]], None]):
        TASK_REGISTRY[name] = fn
        return fn
    return decorator

def run_admission_pipeline(repo_path: str, repo_info: Dict[str, Any], task_names: list):
    if "metadata" not in repo_info or not isinstance(repo_info["metadata"], dict):
        repo_info["metadata"] = {}
    for name in task_names:
        fn = TASK_REGISTRY.get(name)
        if not fn:
            logger.warning(f"[admission] No registered admission task '{name}'")
            continue
        try:
            logger.debug(f"[admission] Executing '{name}' on repo {repo_info.get('repo_name')}")
            fn(repo_path, repo_info)
        except Exception as e:
            logger.warning(f"[admission] Task '{name}' failed on {repo_info.get('repo_name')}: {e}")
    return repo_info

# -- Dynamically import all tasks in modules/admission/* when this package is loaded --
def load_admission_tasks():
    pkg = sys.modules[__name__]
    for _, modname, _ in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        importlib.import_module(modname)
load_admission_tasks()
