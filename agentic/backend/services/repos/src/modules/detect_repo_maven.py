# modules/detect_repo_maven.py

import os
import argparse
import xml.etree.ElementTree as ET
import json
from modules.detect_repo_utils import parse_jdk_version

def _get_namespace(element):
    """Extracts the XML namespace from an element's tag."""
    if element.tag.startswith('{'):
        return element.tag[1:].split('}')[0]
    return ''

def _extract_jdk_version_from_pom(pom_path):
    """Extracts project name and the JDK version from a pom.xml file.

    Returns:
        (project_name, jdk_version) where jdk_version is a string or None if not found.
    """
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
    except ET.ParseError:
        return None, None

    ns = _get_namespace(root)
    ns_prefix = f'{{{ns}}}' if ns else ''

    project_name_elem = root.find(f'{ns_prefix}name')
    if project_name_elem is None or not project_name_elem.text:
        artifact_elem = root.find(f'{ns_prefix}artifactId')
        project_name = artifact_elem.text.strip() if artifact_elem is not None and artifact_elem.text else os.path.basename(os.path.dirname(pom_path))
    else:
        project_name = project_name_elem.text.strip()

    jdk_version = None
    properties = root.find(f'{ns_prefix}properties')
    if properties is not None:
        source_elem = properties.find('maven.compiler.source')
        if source_elem is None:
            source_elem = properties.find(f'{ns_prefix}maven.compiler.source')
        if source_elem is not None and source_elem.text:
            jdk_version = source_elem.text.strip()

    if not jdk_version:
        build = root.find(f'{ns_prefix}build')
        if build is not None:
            plugins = build.find(f'{ns_prefix}plugins')
            if plugins is not None:
                for plugin in plugins.findall(f'{ns_prefix}plugin'):
                    artifact = plugin.find(f'{ns_prefix}artifactId')
                    if artifact is not None and artifact.text and artifact.text.strip() == 'maven-compiler-plugin':
                        configuration = plugin.find(f'{ns_prefix}configuration')
                        if configuration is not None:
                            release = configuration.find(f'{ns_prefix}release')
                            if release is not None and release.text:
                                jdk_version = release.text.strip()
                                break
                            source = configuration.find(f'{ns_prefix}source')
                            if source is not None and source.text:
                                jdk_version = source.text.strip()
                                break
    return project_name, jdk_version

def _scan_maven_projects(directory):
    """Recursively scans for pom.xml files and extracts JDK version info.

    Returns:
         A list of dictionaries [{'project_name': ..., 'version': ...}, ...]
    """
    results = []
    for dirpath, _, filenames in os.walk(directory):
        if 'pom.xml' in filenames:
            pom_path = os.path.join(dirpath, 'pom.xml')
            project_name, version = _extract_jdk_version_from_pom(pom_path)
            if project_name and version:
                results.append({
                    "project_name": project_name,
                    "version": version
                })
    return results

def detect_jdk_version(directory):
    """Detects the highest explicit JDK version among Maven projects in the given directory.

    Returns:
        The highest JDK version as a string, or None if no version info is found.
    """
    projects = _scan_maven_projects(directory)
    if not projects:
        return None

    max_version = None
    for proj in projects:
        parsed_version = parse_jdk_version(proj["version"])
        if parsed_version is not None:
            if max_version is None or parsed_version > max_version:
                max_version = parsed_version

    if max_version is None:
        return None
    return str(max_version)
