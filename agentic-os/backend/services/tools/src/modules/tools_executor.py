# modules/tools_executor.py

import time
import json
import traceback
import os
from pprint import pformat

from shared.logger import logger
from shared.config import config
from modules.tools_registry import get_global_registry
from shared.client_repos import ReposClient

# Instantiate a single shared client
repos_client = ReposClient()


def execute_tool(
    tool_name: str,
    input_args: dict,
    repo_url: str,
    repo_name: str,
    repo_owner: str = None,
    metadata: dict = None,
    turn_id: str = None
) -> dict:
    """
    Executes the named tool (a Python callable) with the given args.
    Before calling the tool, injects repository/context into our in-process config
    so that tools can read REPO_URL, REPO_NAME, REPO_OWNER, REPO_DIR, JDK_VERSION, and METADATA.

    Always returns a dict with:
      - execution_time: float seconds taken
      - status: "success" or "failure"
      - error: error message (empty on success)
      - response: the tool's output as a dict (empty on failure)
    """

    # 1) Retrieve the registry and look up our tool
    registry = get_global_registry()
    record = registry.get(tool_name)
    if not record or "executor" not in record:
        logger.error(
            "Tool '%s' not found in registry. Available tools: %s",
            tool_name, list(registry.keys())
        )
        err = f"Tool '{tool_name}' not found in registry"
        return {
            "execution_time": 0.0,
            "status": "failure",
            "error": err,
            "response": {}
        }
    executor = record["executor"]

    # 2) Compute & inject REPO_DIR = <REPOS_DIR>/<repo_name>
    base_repos = config.get("REPOS_DIR")
    if not base_repos:
        raise RuntimeError("REPOS_DIR must be set in config before executing tools")
    full_repo_dir = os.path.join(base_repos, repo_name)
    config.set("REPO_DIR", full_repo_dir)

    # 3) Inject initial context: repo_url, repo name, passed owner, metadata
    config.set("REPO_URL",   repo_url)
    config.set("REPO_NAME",  repo_name)
    config.set("REPO_OWNER", repo_owner)
    config.set("METADATA",   metadata or {})

    # 4) Fetch JDK/version metadata only if not already a local clone
    if os.path.isdir(full_repo_dir):
        logger.debug("Local repo '%s' exists, skipping metadata fetch", full_repo_dir)
        info_owner = repo_owner
        jdk_version = None
    else:
        lookup = f"{repo_owner}/{repo_name}" if repo_owner else repo_name
        try:
            repo_info = repos_client.get_repo_info(lookup)
            info_owner = repo_owner or repo_info.get("repo_owner") or repo_info.get("owner")
            jdk_version = repo_info.get("jdk_version")
        except Exception as e:
            logger.warning(
                "Could not fetch repository info for '%s': %s. Proceeding without metadata.",
                lookup, e
            )
            info_owner = repo_owner
            jdk_version = None

    # 5) Inject resolved owner & JDK version
    config.set("REPO_OWNER", info_owner)
    config.set("JDK_VERSION", jdk_version)

    # 6) Prepare the arguments for the executor (do NOT inject turn_id)
    args = dict(input_args or {})

    # 6a) Strip & log invocation_reason if enabled
    if config.get("INVOCATION_REASON_ENABLED", False):
        reason = args.pop("invocation_reason", None)
        if reason:
            logger.info("Tool '%s' invoked because: %s", tool_name, reason)

    # 6b) Strip & log turns_to_purge if enabled
    if config.get("TURNS_TO_PURGE_ENABLED", False):
        turns_to_purge = args.pop("turns_to_purge", None)
        if turns_to_purge is not None:
            logger.info("Tool '%s' requests purge of turns: %s", tool_name, turns_to_purge)

    logger.info(
        "Executing tool '%s' (turn_id=%s) in repo '%s' (owner=%s, JDK=%s) with args:\n%s",
        tool_name, turn_id, repo_name, info_owner, jdk_version, pformat(args)
    )

    # 7) Call the tool, catching exceptions
    start = time.time()
    try:
        result = executor(**args)
    except Exception as e:
        elapsed = time.time() - start
        tb = traceback.format_exc()
        err = (
            f"Tool '{tool_name}' execution error: {e}\n"
            f"--- traceback ---\n"
            f"{tb}"
            f"--- end traceback ---"
        )
        logger.error(err)
        return {
            "execution_time": elapsed,
            "status": "failure",
            "error": err,
            "response": {}
        }
    elapsed = time.time() - start

    # 8) Normalize the tool’s return value into JSON/dict
    if isinstance(result, str):
        try:
            result_json = json.loads(result)
        except json.JSONDecodeError as je:
            # Treat invalid JSON as a hard failure
            raw = result[:500] + ("…" if len(result) > 500 else "")
            err = (
                f"Invalid JSON returned by tool '{tool_name}': {je}\n"
                f"Raw output (truncated to 500 chars):\n{raw}"
            )
            logger.error(err)
            return {
                "execution_time": elapsed,
                "status": "failure",
                "error": err,
                "response": {"output_text": result}
            }
        except Exception as e:
            err = f"Unexpected error decoding JSON from tool '{tool_name}': {e}"
            logger.error(err, exc_info=True)
            return {
                "execution_time": elapsed,
                "status": "failure",
                "error": err,
                "response": {}
            }
    elif isinstance(result, dict):
        result_json = result
    else:
        err = f"Unexpected return type from tool '{tool_name}': {type(result)}"
        logger.error(err)
        raw = repr(result)[:500]
        return {
            "execution_time": elapsed,
            "status": "failure",
            "error": err + "\nRaw result repr: " + raw,
            "response": {}
        }

    # 9) Determine overall status & error message
    success = bool(result_json.get("success", True))
    status_text = "success" if success else "failure"

    if success:
        error_msg = ""
    else:
        # Prefer explicit 'error', then 'task_result' or 'output'
        error_msg = (
            result_json.get("error")
            or result_json.get("task_result")
            or result_json.get("output")
        )
        # If still empty, dump the full payload minus 'success'
        if not error_msg:
            fallback = dict(result_json)
            fallback.pop("success", None)
            error_msg = f"No explicit error; full response payload:\n{pformat(fallback)}"

    logger.info(
        "Tool '%s' finished in %.3f sec | status=%s | error=%r",
        tool_name, elapsed, status_text, error_msg
    )
    return {
        "execution_time": elapsed,
        "status": status_text,
        "error": error_msg,
        "response": result_json,
    }


if __name__ == "__main__":
    # Dummy executor for standalone testing
    def dummy_exec(**kwargs):
        return json.dumps({
            "success": True,
            "output": f"Processed args: {kwargs}"
        })

    # Build a minimal registry
    dummy_registry = {"tool_dummy": {"executor": dummy_exec}}
    def get_global_registry():
        return dummy_registry

    # Monkey-patch repos_client for standalone testing
    class DummyReposClient:
        def get_repo_info(self, name):
            return {"repo_owner": "alice", "jdk_version": "11"}
    repos_client = DummyReposClient()

    # Execute with sample context
    res = execute_tool(
        "tool_dummy",
        {"param": "value"},
        repo_url="https://github.com/alice/example-repo.git",
        repo_name="example-repo",
        repo_owner="alice",
        metadata={"foo": "bar"},
        turn_id="1"
    )
    print(json.dumps(res, indent=2))
