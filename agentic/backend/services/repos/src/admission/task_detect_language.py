# admission/task_detect_language.py

from admission import admission_task
from modules.detect_repo import (
    detect_project_type,
    detect_jdk_version,
    detect_gradle_version,
    detect_maven_version,
)

@admission_task("detect_language")
def detect_language_task(repo_path, repo_info):
    """
    Detects project language, build system (Maven/Gradle) and their versions,
    plus the JDK version for Java projects. Populates repo_info['metadata'] with:
      - language
      - build_system
      - build_system_version
      - jdk_version
    """
    # Use the most up-to-date repo path
    local_path = repo_info.get("local_path", repo_path)

    # 1) Identify raw project type: 'java', 'maven', 'gradle', 'python', etc.
    proj_type = detect_project_type(local_path)

    # 2) Normalize language/build_system
    if proj_type in ("maven", "gradle"):
        language     = "java"
        build_system = proj_type
    else:
        language     = proj_type
        build_system = None

    # Ensure metadata dict exists
    md = repo_info.setdefault("metadata", {})
    md["language"]     = language
    md["build_system"] = build_system

    # 3) Detect build-system version if applicable
    if build_system == "gradle":
        md["build_system_version"] = detect_gradle_version(local_path)
    elif build_system == "maven":
        md["build_system_version"] = detect_maven_version(local_path)
    else:
        md["build_system_version"] = None

    # 4) Detect JDK version for Java projects
    if language == "java":
        md["jdk_version"] = detect_jdk_version(local_path)
    else:
        md["jdk_version"] = None
