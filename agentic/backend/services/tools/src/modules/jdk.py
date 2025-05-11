# modules/jdk.py

"""
Switch the repository's required JDK version via SDKMAN.

• Uses dynamic detection (with SDKMAN_DISABLE_PAGER set) to determine available Zulu versions.
• Installs the candidate only if needed and sets it as default via "sdk default java".
• Then validates the setting by running "java -version" in a new clean shell.
"""

from shared.logger import logger
logger = logger
from shared.config import config
import subprocess
import re
import os
from packaging.version import parse as parse_version

DEFAULT_ZULU_MAPPING = {
    "8": "8.0.442-zulu",
    "11": "11.0.16-zulu",
    "17": "17.0.7-zulu",
    "18": "18.0.2-zulu",
}

def get_current_jdk_version():
    try:
        # Unset JAVA_HOME so the fresh environment picks up SDKMAN’s settings
        env = os.environ.copy()
        env.pop("JAVA_HOME", None)
        result = subprocess.run(
            "java -version",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        output = result.stdout.strip() or result.stderr.strip()
        match = re.search(r'"(\d+\.\d+\.\d+)"', output)
        return match.group(1) if match else output
    except Exception as e:
        logger.error("Error detecting current JDK version: %s", e)
        return ""

def get_latest_zulu_version(major_version):
    try:
        sdkman_init = config.get("SDKMAN_INIT_SCRIPT", "source $HOME/.sdkman/bin/sdkman-init.sh")
        command = f"bash -c 'export SDKMAN_DISABLE_PAGER=true; {sdkman_init} && sdk list java'"
        result = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        raw_output = result.stdout + result.stderr
        candidates = []
        for line in raw_output.splitlines():
            if "zulu" in line.lower() and "jre" not in line.lower():
                match = re.search(r'(\d+\.\d+\.\d+)(?:\.fx)?-zulu', line)
                if match:
                    candidate = match.group(1) + "-zulu"
                    if candidate.startswith(f"{major_version}."):
                        candidates.append(candidate)
        if candidates:
            candidates = sorted(candidates, key=lambda v: parse_version(v.split("-")[0]))
            return candidates[-1]
        raise Exception("No matching zulu version found.")
    except Exception as e:
        logger.warning("Dynamic detection failed (%s). Falling back.", e)
        return DEFAULT_ZULU_MAPPING.get(str(major_version), "")

def get_sdkman_version(version_identifier):
    return version_identifier if '-' in version_identifier else get_latest_zulu_version(version_identifier)

def switch_jdk_and_validate(sdkman_version):
    full_sdkman_version = get_sdkman_version(sdkman_version)
    if not full_sdkman_version:
        logger.error("Could not determine SDKMAN version for input: %s", sdkman_version)
        return

    logger.info("Current java version: %s", get_current_jdk_version())

    sdkman_init = config.get("SDKMAN_INIT_SCRIPT", "source $HOME/.sdkman/bin/sdkman-init.sh")
    # Create a fresh subprocess environment – unset JAVA_HOME so sdkman-init.sh sets it correctly.
    env = os.environ.copy()
    env.pop("JAVA_HOME", None)
    env["SDKMAN_NON_INTERACTIVE"] = "true"

    # Check if the needed candidate is already the default.
    check_command = f"bash -c 'export SDKMAN_DISABLE_PAGER=true; {sdkman_init} && sdk current java'"
    try:
        result = subprocess.run(
            check_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        current_output = result.stdout + result.stderr
    except Exception as e:
        logger.error("Error checking current sdk java: %s", e)
        current_output = ""

    need_install = full_sdkman_version not in current_output

    if need_install:
        install_cmd = (
            "if [ -z \"$(sdk list java | grep '" + full_sdkman_version + "' | grep -i installed)\" ]; then "
            "sdk install java " + full_sdkman_version + " --non-interactive; "
            "fi; "
        )
    else:
        install_cmd = ""

    # The command chain now installs the candidate if needed and sets it as default.
    # We no longer call "java -version" here to avoid extra output.
    command_chain = (
        "bash -c '"
        f"{sdkman_init}; {install_cmd}"
        "sdk default java " + full_sdkman_version + "'"
    )

    logger.info("Setting default JDK to %s", full_sdkman_version)
    try:
        result = subprocess.run(
            command_chain,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
            env=env
        )
    except subprocess.TimeoutExpired as te:
        logger.error("Command timed out: %s", te)
        return
    except Exception as e:
        logger.error("Command execution error: %s", e)
        return

    if result.returncode != 0:
        logger.error("Error switching JDK:\n%s", result.stderr.strip())

    # Final validation: run java -version in a clean shell to confirm the new default is active.
    try:
        final_cmd = f"bash -c 'export SDKMAN_DISABLE_PAGER=true; {sdkman_init} && java -version'"
        final_ver = subprocess.run(
            final_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        final_output = final_ver.stdout.strip() or final_ver.stderr.strip()
        logger.info("Final java -version output:\n%s", final_output)
    except Exception as e:
        logger.error("Final validation error: %s", e)

if __name__ == "__main__":
    import sys
    version_input = sys.argv[1] if len(sys.argv) > 1 else "17"
    switch_jdk_and_validate(version_input)
