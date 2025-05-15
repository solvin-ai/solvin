# modules/detect_repo.py

import os
import argparse
import re
import subprocess

from modules.detect_repo_gradle import detect_jdk_version as gradle_detect_jdk_version
from modules.detect_repo_maven  import detect_jdk_version as maven_detect_jdk_version

def detect_project_type(directory):
    """
    Determines the project type in the given directory:
    Returns one of: 'python', 'gradle', 'maven', or 'unknown'
    """
    python_files = ["setup.py", "pyproject.toml", "requirements.txt"]
    gradle_files = ["gradlew", "build.gradle", "settings.gradle"]
    maven_file   = "pom.xml"

    def found(fname):
        return os.path.exists(os.path.join(directory, fname))

    if any(found(f) for f in python_files):
        return "python"
    elif any(found(f) for f in gradle_files):
        return "gradle"
    elif found(maven_file):
        return "maven"
    else:
        return "unknown"


def detect_jdk_version(directory):
    """
    Detects the highest explicit JDK version for a repository that uses
    either Gradle or Maven, by delegating to their specific detectors.
    Returns the JDK version string or None.
    """
    pt = detect_project_type(directory)
    if pt == "gradle":
        return gradle_detect_jdk_version(directory)
    elif pt == "maven":
        return maven_detect_jdk_version(directory)
    else:
        return None


def detect_gradle_version(directory):
    """
    Reads gradle/wrapper/gradle-wrapper.properties to extract the Gradle version.
    """
    wrapper_props = os.path.join(
        directory, "gradle", "wrapper", "gradle-wrapper.properties"
    )
    if not os.path.exists(wrapper_props):
        return None

    try:
        with open(wrapper_props, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("distributionUrl"):
                    # format: distributionUrl=.../gradle-6.8.3-bin.zip
                    _, url = line.split("=", 1)
                    m = re.search(r"gradle-([0-9.]+(?:\.[0-9.]+)*)-bin", url)
                    if m:
                        return m.group(1)
    except Exception:
        pass

    return None


def detect_maven_version(directory):
    """
    Runs 'mvn -v' in the repo and parses 'Apache Maven X.Y.Z' from stdout.
    """
    try:
        out = subprocess.check_output(
            ["mvn", "-v"],
            cwd=directory,
            stderr=subprocess.DEVNULL,
            timeout=10
        ).decode("utf-8", errors="ignore")
        first = out.splitlines()[0]
        m = re.search(r"Apache Maven\s+([0-9.]+)", first)
        if m:
            return m.group(1)
    except Exception:
        pass

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect project type, JDK version, and build-tool version."
    )
    parser.add_argument(
        "directory", nargs="?", default=".", help="Repository directory to scan"
    )
    args = parser.parse_args()

    pt = detect_project_type(args.directory)
    print(f"Detected project type: {pt}")

    jdk = detect_jdk_version(args.directory)
    print(f"Detected JDK version: {jdk or 'none'}")

    if pt == "gradle":
        gv = detect_gradle_version(args.directory)
        print(f"Detected Gradle version: {gv or 'none'}")
    elif pt == "maven":
        mv = detect_maven_version(args.directory)
        print(f"Detected Maven version: {mv or 'none'}")
