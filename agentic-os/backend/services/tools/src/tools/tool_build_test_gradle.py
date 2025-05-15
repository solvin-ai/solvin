# tools/tool_build_test_gradle.py

import os
import subprocess
import re

from shared.config import config
from shared.logger import logger
from modules.tools_safety import get_repo_path, resolve_repo_path, mask_output
from modules.gradle_parser import parse_gradle_build_log_as_nested_json as parse_gradle_build_log

def tool_build_test_gradle(gradle_args: list = None):
    """
    Executes Gradle tests and processes the output.

    Optional Parameter:
      • gradle_args (list of strings): Additional Gradle task arguments.
        When provided, these will override the default test tasks ["clean", "test"]
        (and any discovered extra tasks, like "jacocoTestReport", are ignored).
        If an empty list is provided, then the default tasks *plus* discovered extras are used.
        If omitted, default + discovered extras are used.

    Returns a dict with:
      - "success": True if tests pass, False otherwise.
      - "output": a nested JSON string with parsed test output, or an error message.
    """
    # --- sandbox safety ---
    repo      = config["REPO_NAME"]
    repo_root = get_repo_path(repo)
    repo_path = resolve_repo_path(repo, ".")

    logger.debug("[tool_build_test_gradle] Resolved repo_path: %s, cwd: %s", repo_path, os.getcwd())

    # discover additional tasks (e.g. jacocoTestReport)
    additional_tasks = []
    build_gradle_file = os.path.join(repo_path, "build.gradle")
    if os.path.exists(build_gradle_file):
        try:
            with open(build_gradle_file, "r", encoding="utf-8") as f:
                content = f.read()
            if re.search(r"\bjacocoTestReport\b", content):
                additional_tasks.append("jacocoTestReport")
        except Exception as e:
            logger.warning("Failed to read build.gradle: %s", mask_output(str(e)))

    # determine which tasks to run
    default_tasks = ["clean", "test"]
    if gradle_args is not None:
        if isinstance(gradle_args, list) and all(isinstance(a, str) for a in gradle_args):
            if len(gradle_args) == 0:
                task_args = default_tasks + additional_tasks
            else:
                task_args = gradle_args
        else:
            logger.warning("gradle_args not a list of strings; using default tasks.")
            task_args = default_tasks + additional_tasks
    else:
        task_args = default_tasks + additional_tasks

    # build the command
    gradlew_path = os.path.join(repo_path, "gradlew")
    command = []
    if os.path.exists(gradlew_path):
        try:
            subprocess.run(["chmod", "+x", gradlew_path], check=True)
        except Exception as e:
            logger.warning("Could not make gradlew executable: %s", mask_output(str(e)))
        command.append(gradlew_path)
    else:
        logger.warning("gradlew not found in %s; falling back to system gradle.", mask_output(repo_path))
        command.append("gradle")

    command += [
        "--quiet",
        "--console=plain",
        "--no-daemon",
        "-Dorg.gradle.jvmargs=-Xmx3g",
        "--stacktrace",
    ] + task_args

    logger.trace("Executing command: %s", mask_output(" ".join(command)))

    env = os.environ.copy()
    env["GRADLE_OPTS"] = "-Dorg.gradle.daemon=false -Dfile.encoding=UTF-8"

    try:
        result = subprocess.run(
            command,
            cwd=repo_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        raw_output = result.stderr or ""

        # parse into nested JSON if possible
        json_output = parse_gradle_build_log(
            raw_output,
            repo_root=repo_path,
            msg_type="error",
            summary_marker="tests completed"
        )
        final_output = json_output if json_output else raw_output

        build_success = (result.returncode == 0)
        if build_success and not final_output:
            final_output = "Gradle tests ran successfully."
        elif not build_success and not final_output:
            final_output = f"Gradle tests failed with return code {result.returncode}."

        return {"success": build_success, "output": mask_output(final_output)}

    except Exception as e:
        logger.exception("Error running Gradle tests: %s", mask_output(str(e)))
        return {"success": False, "output": mask_output(str(e))}


def get_tool():
    """
    Returns the tool specification for running Gradle tests.
    A user may optionally provide a property 'gradle_args', an array of strings,
    to override the default test tasks.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_build_test_gradle",
            "description": (
                "Runs Gradle tests and processes the test output by extracting error "
                "blocks in a nested JSON format. Optionally accepts 'gradle_args' "
                "to override default test tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gradle_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of Gradle task arguments to override the "
                            "default ['clean', 'test'] tasks."
                        )
                    }
                },
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
