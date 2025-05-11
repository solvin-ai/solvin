# modules/agents_tasks.py

"""
Task‐API client for fetching the user prompt for a given task_name.
"""

import requests
from shared.config import config
from shared.logger import logger


def _tasks_api_url() -> str:
    base = config["AGENT_MANAGER_API_URL"].rstrip("/")
    return f"{base}/api/tasks"


def fetch_task_prompt(task_name: str) -> str:
    """
    Fetches the 'task_prompt' string for the given task_name.
    Returns empty string on any error or missing prompt.
    """
    url = _tasks_api_url()
    try:
        resp = requests.get(url, params={"task_name": task_name})
        resp.raise_for_status()
        data = resp.json()

        # handle nested shape { "task": { ..., "task_prompt": ... } }
        prompt = ""
        if isinstance(data, dict):
            task_obj = data.get("task")
            if isinstance(task_obj, dict):
                prompt = task_obj.get("task_prompt", "") or ""
            else:
                prompt = data.get("task_prompt", "") or ""

        if prompt:
            return prompt
        else:
            logger.warning(f"Tasks API returned no valid 'task_prompt' for '{task_name}'")
            return ""
    except Exception as e:
        logger.error(f"Error fetching task prompt for '{task_name}': {e}", exc_info=True)
        return ""
