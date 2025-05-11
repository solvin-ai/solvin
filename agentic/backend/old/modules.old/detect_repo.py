# modules/detect_version.py

import os
import argparse
from modules.detect_repo_gradle import detect_jdk_version as gradle_detect_jdk_version
from modules.detect_repo_maven import detect_jdk_version as maven_detect_jdk_version

def detect_jdk_version(directory):
    """
    Detects the highest explicit JDK version for a repository that uses either Gradle or Maven.
    
    It examines if the directory contains Gradle indicators (gradlew, build.gradle, settings.gradle)
    or a Maven pom.xml file, and calls the respective detection function.
    
    Returns:
        The highest JDK version as a string, or None if not found.
    """
    gradle_indicators = ["gradlew", "build.gradle", "settings.gradle"]
    is_gradle = any(os.path.exists(os.path.join(directory, indicator)) for indicator in gradle_indicators)
    is_maven = os.path.exists(os.path.join(directory, "pom.xml"))
    
    if is_gradle and is_maven:
        # If both exist, default to using Gradle detection.
        return gradle_detect_jdk_version(directory)
    elif is_gradle:
        return gradle_detect_jdk_version(directory)
    elif is_maven:
        return maven_detect_jdk_version(directory)
    else:
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect JDK version using Gradle or Maven detection.")
    parser.add_argument("directory", nargs="?", default=".", help="Repository directory to scan")
    args = parser.parse_args()
    version = detect_jdk_version(args.directory)
    if version:
        print(f"Detected JDK version: {version}")
    else:
        print("Could not determine JDK version.")
