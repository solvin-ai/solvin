# modules/detect_repo_gradle.py

"""
A module to detect version information from a repository by invoking Gradle
with an external init script.

This updated script expects that your Gradle init script produces a JSON object of the form:

{
  "jdkVersions": [
    { "project": ":clients", "jdkVersion": "11" },
    { "project": ":connect", "jdkVersion": "17" },
    ...
  ],
  "gradle": {
    "gradleRequiredVersion": "8.10.2",
    "runningGradleVersion": "8.13"
  }
}

Public API:
  • detect_jdk_versions(repo_path): returns the list of explicit project/JDK objects.
  • detect_jdk_version(repo_path): returns the highest explicit JDK version as a string.
  • detect_gradle_version(repo_path): returns the Gradle version object from the root.
  • detect_versions(repo_path): returns a dict with both pieces of information.

This approach avoids parsing legacy files by instead invoking Gradle using your universal‑init.gradle init script.
"""

import os
import re
import sys
import subprocess
import json
from modules.logs import logger  # Make sure that modules/logs.py exists and defines logger
from modules.detect_repo_utils import parse_jdk_version

# Default settings.
DEFAULT_GRADLE_EXECUTABLE = "gradle"
DEFAULT_GRADLE_TASK = "tasks"   # A task used to force project evaluation.
DEFAULT_INIT_SCRIPT = "universal-init.gradle"

def get_init_script_path(init_script=DEFAULT_INIT_SCRIPT):
    """
    Determines the absolute path to the Gradle init script.
    If the provided init_script path is relative, it is interpreted as relative to this file's directory.
    Returns the absolute path if found, otherwise None.
    """
    if not os.path.isabs(init_script):
        # Look relative to the location of this file.
        init_script_path = os.path.join(os.path.dirname(__file__), init_script)
    else:
        init_script_path = init_script

    if not os.path.exists(init_script_path):
        logger.error("Gradle init script not found at %s", init_script_path)
        return None

    return init_script_path

def get_versions_via_gradle(repo_path, gradle_executable=DEFAULT_GRADLE_EXECUTABLE,
                              gradle_task=DEFAULT_GRADLE_TASK, init_script=DEFAULT_INIT_SCRIPT):
    """
    Invokes Gradle with the specified init script.
    Expects the init script to print a JSON object with two keys:
      - "jdkVersions": list of objects containing "project" and "jdkVersion"
      - "gradle": object with Gradle version info (gradleRequiredVersion and runningGradleVersion)
    Parameters:
       repo_path: The repository root directory.
       gradle_executable: Command name (default "gradle").
       gradle_task: Task to run (default "tasks").
       init_script: Path to the Gradle init script (default universal‑init.gradle).
    Returns:
       A dictionary parsed from the JSON output or None if extraction/parsing fails.
    """
    init_script_path = get_init_script_path(init_script)
    if not init_script_path:
        logger.error("Gradle init script not found.")
        return None

    cmd = [gradle_executable, "--init-script", init_script_path, gradle_task]
    logger.debug("Running Gradle command: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, cwd=repo_path, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            logger.error("Gradle command returned non-zero exit code %s. Stderr: %s",
                         proc.returncode, proc.stderr)
        output = proc.stdout

        # Look for a JSON object in the output.
        pattern = re.compile(r"(\{.*\})", re.DOTALL)
        match = pattern.search(output)
        if match:
            json_str = match.group(1)
            try:
                data = json.loads(json_str)
                logger.debug("Extracted JSON: %s", data)
                return data
            except Exception as e:
                logger.error("Error parsing JSON from Gradle output: %s", e)
                return None
        else:
            logger.error("Could not find JSON output in Gradle output.")
            return None
    except Exception as exc:
        logger.error("Exception running Gradle command: %s", exc)
        return None

def detect_jdk_versions(repo_path):
    """
    Invokes Gradle with the init script and returns the list of explicit JDK version settings.
    Each entry in the list is an object containing the project path and its explicitly set JDK version.
    """
    data = get_versions_via_gradle(repo_path)
    if data is None:
        logger.info("No version information detected via Gradle init script in repository: %s", repo_path)
        return None
    # Expecting a key "jdkVersions" in the JSON object.
    jdk_list = data.get("jdkVersions")
    if not jdk_list:
        logger.info("No explicit JDK versions found in repository: %s", repo_path)
        return None
    return jdk_list

def detect_jdk_version(repo_path):
    """
    Returns the highest explicit JDK version among all projects.
    It calls detect_jdk_versions(repo_path) to get a list of project objects (each with keys "project" and "jdkVersion"),
    then converts the version strings to integers for comparison using the common parse_jdk_version function.
    Returns the highest version as a string, or None if no explicit version is found.
    """
    jdk_list = detect_jdk_versions(repo_path)
    if not jdk_list:
        logger.info("No explicit JDK versions detected in repository: %s", repo_path)
        return None

    versions = []
    for item in jdk_list:
        version_str = item.get("jdkVersion", "").strip()
        if not version_str:
            continue
        version_int = parse_jdk_version(version_str)
        if version_int is not None:
            versions.append(version_int)
        else:
            logger.debug("Could not convert jdkVersion '%s' from project %s to int using parse_jdk_version",
                         version_str, item.get("project"))
    if not versions:
        logger.info("No valid explicit JDK versions found in repository: %s", repo_path)
        return None

    max_version = max(versions)
    logger.info("Detected highest explicit JDK version: %s", max_version)
    return str(max_version)

def detect_gradle_version(repo_path):
    """
    Invokes Gradle with the init script and returns the Gradle version information from the root project.
    The returned value is an object with keys: "gradleRequiredVersion" and "runningGradleVersion".
    """
    data = get_versions_via_gradle(repo_path)
    if data is None:
        logger.info("No version information detected via Gradle init script for repository: %s", repo_path)
        return None
    gradle_data = data.get("gradle")
    if not gradle_data:
        logger.info("No Gradle version information found for repository: %s", repo_path)
        return None
    return gradle_data

def detect_versions(repo_path):
    """
    Convenience function that retrieves both the explicit JDK version settings and the Gradle version.
    Returns a dictionary with:
         "jdkVersions": list of project objects with explicit JDK versions,
         "gradle": an object with the Gradle version information.
    """
    data = get_versions_via_gradle(repo_path)
    if data is None:
        logger.info("No version information detected via Gradle init script for repository: %s", repo_path)
        return None
    return data

if __name__ == "__main__":
    # For standalone testing.
    if len(sys.argv) < 2:
        print("Usage: {} <repository_path>".format(sys.argv[0]))
        sys.exit(1)
    repo = sys.argv[1]
    versions = detect_versions(repo)
    if versions:
        print("Detected versions:")
        print(json.dumps(versions, indent=2))
        print("Highest explicit JDK version:", detect_jdk_version(repo))
        print("Gradle version info:", detect_gradle_version(repo))
    else:
        print("No version information detected.")
