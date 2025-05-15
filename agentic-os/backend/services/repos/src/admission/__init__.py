# admission/__init__.py

import pkgutil, importlib, sys
from typing import Callable, Dict, Any
from shared.logger import logger

JOB_REGISTRY = {}

def admission_job(name: str):
    def decorator(fn: Callable[[str, Dict[str, Any]], None]):
        JOB_REGISTRY[name] = fn
        return fn
    return decorator

def run_admission_pipeline(repo_path: str, repo_info: Dict[str, Any], job_names: list):
    if "metadata" not in repo_info or not isinstance(repo_info["metadata"], dict):
        repo_info["metadata"] = {}
    for name in job_names:
        fn = JOB_REGISTRY.get(name)
        if not fn:
            logger.warning(f"[admission] No registered admission job '{name}'")
            continue
        try:
            logger.debug(f"[admission] Executing '{name}' on repo {repo_info.get('repo_name')}")
            fn(repo_path, repo_info)
        except Exception as e:
            logger.warning(f"[admission] Job '{name}' failed on {repo_info.get('repo_name')}: {e}")
    return repo_info

# -- Dynamically import all jobs in modules/admission/* when this package is loaded --
def load_admission_jobs():
    pkg = sys.modules[__name__]
    for _, modname, _ in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        importlib.import_module(modname)
load_admission_jobs()
