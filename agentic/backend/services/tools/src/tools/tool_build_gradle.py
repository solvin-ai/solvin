# tools/tool_build_gradle.py

"""
Runs a Gradle build and extracts error blocks.
Also removes non-relevant Gradle footer advice before parsing.
"""

import os
import subprocess

from shared.config import config
from shared.logger import logger
from modules.tools_safety import (
    get_repo_path,
    resolve_repo_path,
    check_path,
    mask_output,
)
from modules.gradle_parser import parse_gradle_build_log_as_nested_json as parse_gradle_build_log

# Set to True if warnings should also be included; otherwise only errors are extracted.
INCLUDE_WARNINGS = False


def tool_build_gradle(gradle_args: list = None):
    """
    Executes the Gradle build and then parses the compiler output.

    Optional Parameter:
      • gradle_args (list of strings): Additional Gradle task arguments
        (for example, [":some-task"]). When provided, these arguments
        override the default task arguments (which default to ["clean", "build"]).

    Returns a dictionary with keys:
      • "success": (bool) indicating whether the build succeeded,
      • "output": the parsed output (a nested JSON string) or an error message.
    """
    # sandbox safety
    repo = config.get("REPO_NAME")
    if not repo:
        raise RuntimeError("REPO_NAME is not set in config.")
    repo_root = get_repo_path(repo)
    repo_path = resolve_repo_path(repo, ".")

    logger.debug(
        "[tool_build_gradle] Resolved repo_path: %r, cwd: %r",
        repo_path,
        os.getcwd(),
    )

    if isinstance(gradle_args, list) and gradle_args and all(isinstance(arg, str) for arg in gradle_args):
        task_args = gradle_args
    else:
        task_args = ["clean", "build"]

    # Use the config service ONLY for this value
    branch = config.get("GITHUB_FEATURE_BRANCH") or "ee-automated-g11n-yaniv"

    try:
        env = os.environ.copy()
        env["GRADLE_OPTS"] = (
            "-Dorg.gradle.daemon=false "
            "-Dfile.encoding=UTF-8"
        )
        env["GITHUB_FEATURE_BRANCH"] = branch

        gradlew_path = os.path.join(repo_path, "gradlew")
        logger.debug(
            "[tool_build_gradle] Before check_path for gradlew_path: %r, cwd: %r",
            gradlew_path,
            os.getcwd(),
        )
        gradlew_path = check_path(gradlew_path, allowed_root=repo_root)
        logger.debug(
            "[tool_build_gradle] After check_path for gradlew_path: %r, cwd: %r",
            gradlew_path,
            os.getcwd(),
        )

        base_flags = [
            "--quiet",
            "--console=plain",
            "--no-daemon",
            "-Dorg.gradle.jvmargs=-Xmx3g",
            "--stacktrace",
        ]

        if os.path.exists(gradlew_path):
            # Ensure gradlew is executable.
            subprocess.run(["chmod", "+x", gradlew_path], check=True)
            command = [gradlew_path] + base_flags + task_args
        else:
            logger.warning("gradlew not found in %s, falling back to system gradle.", repo_path)
            command = ["gradle"] + base_flags + task_args

        result = subprocess.run(
            command,
            cwd=repo_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        build_success = (result.returncode == 0)
        full_build_output = result.stderr

        json_output = parse_gradle_build_log(
            full_build_output,
            repo_root=repo_path,
            msg_type="both" if INCLUDE_WARNINGS else "error",
        )

        if not build_success and not json_output:
            final_output = full_build_output
        else:
            final_output = json_output if json_output else full_build_output

        return {"success": build_success, "output": mask_output(final_output)}

    except Exception as e:
        logger.exception("Error during Gradle build: %s", e)
        return {"success": False, "output": mask_output(str(e))}


def get_tool():
    """
    Returns the tool specification for Gradle build.
    The user may provide an optional property 'gradle_args' (an array of strings)
    to override the default task arguments.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_build_gradle",
            "description": (
                "Builds the project using Gradle and extracts error messages in a "
                "nested JSON format (grouped by error type, shared paths, and filenames). "
                "Optionally, the caller can provide overriding Gradle task arguments via the "
                "'gradle_args' property. If no 'gradle_args' are provided or an empty list "
                "is given, the default tasks ['clean', 'build'] are used."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gradle_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional Gradle task arguments in place of 'clean build'."
                    }
                },
                "required": [],
                "additionalProperties": False,
                "strict": True,
            },
        },
        "internal": {
            "preservation_policy": "build",
            "type": "readonly",
        },
    }
