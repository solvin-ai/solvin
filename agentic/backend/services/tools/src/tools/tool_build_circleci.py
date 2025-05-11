# tools/tool_build_circleci.py

import os
import time
import json
import datetime
import requests
import subprocess  # For running Git commands.

from shared.config import config
from shared.logger import logger

from modules.tools_safety import (
    get_repos_dir,
    get_log_dir,
    get_repo_path,
    resolve_repo_path,
    check_path,
    mask_output,
)
from modules.gradle_parser import (
    parse_gradle_build_log_as_nested_json as parse_gradle_build_log
)


# ---------------------------------------------------------------------------
# Hard-coded flags for log output filtering:
SHOW_RAW_LOGS_OUTPUT = False
PRINT_CONSOLE_OUTPUT = False

# When parsing the build log output the parser will extract only errors.
INCLUDE_WARNINGS = False

# ---------------------------------------------------------------------------
def load_required_config():
    """
    Loads and validates required configuration settings from the global config.
    Returns a dictionary containing:
      - username
      - vcs_type
      - token
      - api_url
      - api_url_v1 (optional)
    """
    required_keys = [
        "CIRCLECI_USERNAME",
        "CIRCLECI_VCS_TYPE",
        "API_TOKEN_CIRCLECI",
        "API_URL_CIRCLECI",
    ]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        for key in missing:
            logger.error(f"Required configuration key '{key}' is not set.")
        raise ValueError("Missing required configuration keys: " + ", ".join(missing))

    return {
        "username":   config.get("CIRCLECI_USERNAME"),
        "vcs_type":   config.get("CIRCLECI_VCS_TYPE"),
        "token":      config.get("API_TOKEN_CIRCLECI"),
        "api_url":    config.get("API_URL_CIRCLECI"),
        "api_url_v1": config.get("API_URL_CIRCLECI_V1"),  # Optional for v1.1 API.
    }

# ---------------------------------------------------------------------------
def get_epoch(timestamp_str):
    """
    Converts an ISO8601 timestamp (e.g., "2025-02-10T18:02:48Z") to epoch seconds.
    Returns None on conversion error.
    """
    try:
        dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
        dt = dt.replace(tzinfo=datetime.timezone.utc)
        return int(dt.timestamp())
    except Exception as e:
        logger.error(f"Timestamp conversion error for '{timestamp_str}': {e}")
        return None

# ---------------------------------------------------------------------------
def compute_duration(started_at, stopped_at):
    """
    Computes duration between start and stop times.
    If stopped_at is empty, computes duration from now.
    """
    if not started_at:
        return "N/A"
    start_sec = get_epoch(started_at)
    if start_sec is None:
        return "N/A"

    if stopped_at:
        end_sec = get_epoch(stopped_at)
        diff = (end_sec - start_sec) if end_sec else 0
    else:
        diff = int(time.time()) - start_sec

    duration = time.strftime('%H:%M:%S', time.gmtime(diff))
    if not stopped_at:
        duration += " (running)"
    return duration

# ---------------------------------------------------------------------------
class CircleCIClient:
    """
    A client for interacting with the CircleCI APIs:
      - v2 for pipelines, workflows, and jobs.
      - v1.1 for job steps and console output.
    """
    def __init__(self, username, vcs_type, token, api_url, api_url_v1=None):
        self.username   = username
        self.vcs_type   = vcs_type
        self.token      = token
        self.api_url    = api_url.rstrip("/")
        self.api_url_v1 = api_url_v1 or self._derive_v1_url()

    def _derive_v1_url(self):
        url = self.api_url
        if url.endswith("/v2"):
            url = url.rsplit("/v2", 1)[0]
        return f"{url}/v1.1"

    def get_latest_pipeline_id(self, project, branch="main"):
        url     = f"{self.api_url}/project/{self.vcs_type}/{self.username}/{project}/pipeline"
        params  = {"branch": branch, "limit": 1}
        headers = {"Circle-Token": self.token}
        resp    = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data    = resp.json()
        return data.get("items", [{}])[0].get("id", "")

    def get_workflows(self, pipeline_id):
        url     = f"{self.api_url}/pipeline/{pipeline_id}/workflow"
        headers = {"Circle-Token": self.token}
        resp    = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json().get("items", [])

    def get_workflow_jobs(self, workflow_id):
        url     = f"{self.api_url}/workflow/{workflow_id}/job"
        headers = {"Circle-Token": self.token}
        resp    = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json().get("items", [])

    def get_job_steps(self, job_number, project):
        url = (
            f"{self.api_url_v1}/project/{self.vcs_type}/{self.username}/"
            f"{project}/{job_number}?circle-token={self.token}"
        )
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json().get("steps", [])

    def get_action_logs(self, action):
        logs = []
        output_url = action.get("output_url")
        if output_url and output_url != "null":
            if "circle-token=" not in output_url:
                sep = "&" if "?" in output_url else "?"
                output_url = f"{output_url}{sep}circle-token={self.token}"
            resp = requests.get(output_url)
            resp.raise_for_status()
            logs = resp.json()
        else:
            logs = action.get("output", [])
        return logs

# ---------------------------------------------------------------------------
def fetch_pipeline_details(client, project, branch, pipeline_id, workflow_id=""):
    """
    Retrieves pipeline → workflows → jobs → steps → actions → logs.
    Applies SHOW_RAW_LOGS_OUTPUT / PRINT_CONSOLE_OUTPUT filters.
    """
    result = {"pipeline_id": pipeline_id, "workflows": []}
    workflows = client.get_workflows(pipeline_id)
    if workflow_id:
        workflows = [w for w in workflows if w.get("id") == workflow_id]
    if not workflows:
        raise ValueError("No workflows found.")

    for wf in workflows:
        wf_dict = {"id": wf.get("id"), "jobs": []}
        for job in client.get_workflow_jobs(wf.get("id")):
            job_name   = job.get("name", "Unknown")
            job_number = job.get("job_number", "N/A")
            status     = job.get("status", "Unknown")
            started    = job.get("started_at", "N/A")
            stopped    = job.get("stopped_at", "")
            duration   = compute_duration(started, stopped)

            job_dict = {
                "name":       job_name,
                "job_number": job_number,
                "job_id":     job.get("id", ""),
                "status":     status,
                "started_at": started,
                "duration":   duration,
                "steps":      [],
            }

            try:
                steps = client.get_job_steps(job_number, project)
            except Exception as e:
                logger.error(f"Error retrieving steps for job '{job_number}': {e}")
                steps = []

            for step in steps:
                step_dict = {"name": step.get("name", "Unknown"), "actions": []}
                for action in step.get("actions", []):
                    a_status = action.get("status", "Unknown")
                    has_out  = action.get("has_output", False)
                    a_dict   = {"status": a_status, "has_output": has_out, "logs": None}

                    if has_out:
                        try:
                            raw_logs = client.get_action_logs(action)
                            if SHOW_RAW_LOGS_OUTPUT:
                                a_dict["logs"] = raw_logs
                            else:
                                msgs = []
                                if isinstance(raw_logs, list):
                                    for entry in raw_logs:
                                        msg = entry.get("message", "")
                                        if (PRINT_CONSOLE_OUTPUT or
                                            any(kw in msg.lower() for kw in ("error", "fail", "warning"))):
                                            msgs.append(msg)
                                else:
                                    msgs = raw_logs
                                a_dict["logs"] = msgs
                        except Exception as e:
                            logger.error(f"Error retrieving logs for action in step '{step_dict['name']}': {e}")

                    step_dict["actions"].append(a_dict)

                job_dict["steps"].append(step_dict)

            wf_dict["jobs"].append(job_dict)
        result["workflows"].append(wf_dict)

    return result

# ---------------------------------------------------------------------------
def wait_for_pipeline_completion(client, project, branch, pipeline_id, interval=20, timeout=1800):
    """
    Polls until no jobs are in active states, then returns full pipeline details.
    """
    start = time.time()
    while True:
        try:
            details = fetch_pipeline_details(client, project, branch, pipeline_id)
        except Exception as e:
            logger.error(f"Error fetching pipeline details during poll: {e}")
            details = {"workflows": []}

        all_done = True
        for wf in details["workflows"]:
            for job in wf["jobs"]:
                st = job.get("status", "").lower()
                if st in ("running", "queued", "not_run", "scheduled", "on_hold"):
                    all_done = False
                    break
            if not all_done:
                break

        if all_done:
            logger.info("All pipeline jobs have completed.")
            return details

        if time.time() - start > timeout:
            raise TimeoutError("Timed out waiting for pipeline to complete.")

        logger.info(f"Waiting for pipeline to complete... sleeping for {interval}s")
        time.sleep(interval)

# ---------------------------------------------------------------------------
def tool_build_circleci():
    """
    Runs a Git commit/push to trigger a CircleCI build, waits for it,
    aggregates the Gradle build output, parses errors as nested JSON,
    then reverts the commit.

    Returns:
      {
        "success": bool,
        "output":  masked string (JSON or raw logs)
      }
    """
    # --- Sandbox safety: locate & lock down the repo path ---
    repo_name = config["REPO_NAME"]
    repo_root = get_repo_path(repo_name)
    repo_path = resolve_repo_path(repo_name, ".")
    # resolve_repo_path already enforces the path lives under repo_root

    branch_name = config.get("GITHUB_FEATURE_BRANCH", "main")

    try:
        # Git operations
        logger.info("Staging all changes...")
        subprocess.run(["git", "add", "."], check=True, cwd=repo_path)

        logger.info("Committing with message 'Automated g11n migration'...")
        subprocess.run(
            ["git", "commit", "-m", "Automated g11n migration"],
            check=True, cwd=repo_path
        )

        logger.info(f"Pushing to branch '{branch_name}' to trigger CircleCI...")
        subprocess.run(
            ["git", "push", "--set-upstream", "origin", branch_name],
            check=True, cwd=repo_path
        )

        # CircleCI API
        cfg    = load_required_config()
        client = CircleCIClient(
            cfg["username"],
            cfg["vcs_type"],
            cfg["token"],
            cfg["api_url"],
            cfg.get("api_url_v1"),
        )

        pipeline_id = client.get_latest_pipeline_id(repo_name, branch_name)
        if not pipeline_id:
            return {"success": False, "output": mask_output("Pipeline ID could not be determined.")}

        logger.info("Waiting for CircleCI pipeline to complete...")
        details = wait_for_pipeline_completion(client, repo_name, branch_name, pipeline_id)

        # Aggregate Gradle logs
        logs_list      = []
        overall_success = True

        for wf in details["workflows"]:
            for job in wf["jobs"]:
                if "gradle" not in job["name"].lower():
                    continue
                if job["status"].lower() != "success":
                    overall_success = False
                for step in job["steps"]:
                    for action in step["actions"]:
                        act_logs = action.get("logs")
                        if not act_logs:
                            continue
                        if isinstance(act_logs, list):
                            logs_list.append("\n".join(act_logs))
                        else:
                            logs_list.append(act_logs)

        aggregated = "\n".join(logs_list)

        # Parse with our Gradle parser
        parsed = parse_gradle_build_log(
            aggregated,
            repo_root=repo_path,
            msg_type=("both" if INCLUDE_WARNINGS else "error")
        )
        final_output = parsed.strip() or aggregated

        # Revert the Git commit
        logger.info("Reverting the commit and force-pushing to undo changes...")
        subprocess.run(["git", "reset", "--soft", "HEAD~1"], check=True, cwd=repo_path)
        subprocess.run(["git", "reset"],              check=True, cwd=repo_path)
        subprocess.run(
            ["git", "push", "--force-with-lease", "origin", branch_name],
            check=True, cwd=repo_path
        )

        return {"success": overall_success, "output": mask_output(final_output)}

    except Exception as e:
        logger.exception("Error during CircleCI build or Git operations")
        return {"success": False, "output": mask_output(str(e))}

# ---------------------------------------------------------------------------
def get_tool():
    """
    Returns the tool specification for the CircleCI pipeline query tool.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_build_circleci",
            "description": (
                "Runs a Git commit/push to trigger a CircleCI build pipeline, "
                "waits for completion, aggregates the Gradle build output, "
                "parses errors into nested JSON, then reverts the commit."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "build",
            "type": "readonly"
        }
    }
