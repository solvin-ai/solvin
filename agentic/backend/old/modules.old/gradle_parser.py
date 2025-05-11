# modules/gradle_parser.py

"""
This module now includes an alternative JSON output function that produces a nested
structure with three levels:
  • Error type (category)
  • Shared directory (path)
  • Shared filename—with an array of error details.

In the updated output, repeated error messages in the same file are grouped so that
each file lists an "errors" array where each entry contains a unique error message and
an array (lines[]) with all the corresponding line numbers.

Additionally, a new function is provided to extract the top-level error message and
the cause for failure from a Gradle stack trace.
"""

import re
import os
import json
import logging
from collections import defaultdict, Counter
from modules.tools_safety import check_path, mask_output

logger = logging.getLogger(__name__)

# Constant to control whether a detailed summary is generated. Default is False.
GENERATE_SUMMARY = False

# Updated regex patterns:
# 1. The primary branch (Option 1) covers headers that start with a filepath (ending in .java or .config)
#    followed by colon, line number, then the level and message.
# 2. Option 2 matches messages where the file info is appended in parentheses.
ERROR_HEADER_PATTERN = re.compile(
    r"""^(?:
         # Option 1: Standard header (e.g., for Java errors or config errors that start with file info)
         (?P<filepath>.+\.(?:java|config)):(?P<line>\d+):\s+(?P<level>error|warning):\s+(?P<message>.+)
         |
         # Option 2: Other style (e.g., configuration file errors)
         (?P<message_alt>.+?)\s*(?::\s*[^\(]+)?\s*\((?P<filepath_alt>.+\.(?:java|config)):(?P<line_alt>\d+)\)$
         )""",
    re.VERBOSE | re.IGNORECASE
)

# Update the GENERAL_HEADER_PATTERN similarly.
GENERAL_HEADER_PATTERN = re.compile(
    r'^.+\.(?:java|config):\d+:\s+(error|warning):\s+.+$', re.IGNORECASE
)

def remove_gradle_footer(build_output):
    return re.sub(
        r"(?s)Run with --stacktrace option to get the stack trace\..*?BUILD FAILED in .*?(?:\n|$)",
        "",
        build_output
    )

def extract_error_blocks(build_output):
    lines = build_output.splitlines()
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if ERROR_HEADER_PATTERN.match(line):
            current_block = [line]
            i += 1
            while i < n:
                next_line = lines[i]
                if GENERAL_HEADER_PATTERN.match(next_line):
                    break
                if next_line.startswith("Note:") or next_line.startswith("FAILURE:") or next_line.startswith("*"):
                    break
                current_block.append(next_line)
                i += 1
            blocks.append("\n".join(current_block))
        else:
            i += 1
    return blocks

def format_error_block(block, repo_root):
    lines = block.splitlines()
    if not lines:
        return block
    m = ERROR_HEADER_PATTERN.match(lines[0])
    if m:
        # Check whether we got Option 1 or Option 2.
        if m.group("filepath"):
            fullpath = m.group("filepath")
            line_num = m.group("line")
            level = m.group("level")
            message = m.group("message")
        elif m.group("filepath_alt"):
            fullpath = m.group("filepath_alt")
            line_num = m.group("line_alt")
            level = "error"   # Default level when not provided.
            message = m.group("message_alt")
        try:
            relative_path = os.path.relpath(fullpath, repo_root)
        except Exception as e:
            logger.warning("Error converting path: %s", e)
            relative_path = fullpath
        # Normalize the relative path to avoid duplications.
        relative_path = os.path.normpath(relative_path)
        if not relative_path.startswith("."):
            relative_path = "./" + relative_path
        # Format the first line.
        lines[0] = f"{relative_path}:{line_num}: {level}: {message}"
    return "\n".join(lines)

def extract_issue_details(block):
    lines = [line for line in block.splitlines() if line.strip()]
    if not lines:
        return (None, None, None, block.strip())
    first_line = lines[0]
    m = ERROR_HEADER_PATTERN.match(first_line)
    if m:
        if m.group("filepath"):
            return (
                m.group("filepath"),
                m.group("line"),
                m.group("level").lower(),
                m.group("message").strip()
            )
        elif m.group("filepath_alt"):
            return (
                m.group("filepath_alt"),
                m.group("line_alt"),
                "error",
                m.group("message_alt").strip()
            )
    return (None, None, None, block.strip())

def categorize_issue(message, level):
    msg_lower = message.lower()
    if level == "warning":
        if "unchecked" in msg_lower:
            return "Warning - Unchecked"
        return "Warning"
    if "cannot find symbol" in msg_lower:
        return "Missing Symbol"
    if "invalid method reference" in msg_lower:
        return "Invalid Method Ref"
    if "constructor" in msg_lower and "cannot be applied" in msg_lower:
        return "Constructor/Enum Mismatch"
    return "Other Error"

def extract_summary_line(build_output, summary_marker=None):
    if summary_marker:
        for line in build_output.splitlines():
            if summary_marker in line:
                return line.strip()
        return ""
    else:
        for line in build_output.splitlines():
            if "Execution failed for task" in line:
                return line.strip()
        return ""

def extract_top_level_error_and_cause(stack_trace):
    """
    Extracts the top-level error message and the first "Caused by:" message from a Gradle stack trace.

    This function looks for the marker line "* Exception is:" and then takes the next non-empty line
    as the top-level error message. It also scans the entire stack trace for the first line that starts
    with "Caused by:".

    Args:
        stack_trace (str): The complete Gradle stack trace.

    Returns:
        tuple:
          (top_error_message, cause_message)
          - top_error_message (str): The extracted top-level error message, or None if not found.
          - cause_message (str): The first "Caused by:" line found, or None.
    """
    lines = stack_trace.splitlines()
    top_error_message = None
    cause_message = None

    # Search for the top-level error message from the "* Exception is:" marker.
    for i, line in enumerate(lines):
        if "* Exception is:" in line:
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate:
                    top_error_message = candidate
                    break
                j += 1
            if top_error_message:
                break

    # Find the first line that starts with "Caused by:".
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("Caused by:"):
            cause_message = stripped_line
            break

    return top_error_message, cause_message

def generate_summary(groups, loc_limit=None, msg_limit=None):
    lines = ["Build Issues Summary:"]
    for cat, data in sorted(groups.items(), key=lambda item: item[1]["count"], reverse=True):
        count = data["count"]
        files = sorted(data["locations"])
        if files and loc_limit:
            file_str = ", ".join(files[:loc_limit])
            if len(files) > loc_limit:
                file_str += f" ... ({len(files)} total)"
        else:
            file_str = ", ".join(files) if files else "None"
        examples = data["messages"].most_common(msg_limit) if msg_limit else data["messages"].most_common()
        msg_str = ", ".join(f'"{msg}" ({cnt}x)' for msg, cnt in examples)
        lines.append(f"[{cat}] {count} issue(s) | Files: {file_str} | Examples: {msg_str}")
    return "\n".join(lines)

def parse_gradle_build_log_as_nested_json(build_output, repo_root=".", msg_type="both", summary_marker=None):
    """
    Parse the Gradle build log and output a nested JSON structure with three levels:
      • Error type (category)
      • Shared paths (directories)
      • Shared filename—which now groups error details by message.

    Each file lists an "errors" array where each entry contains a unique error message and an
    array of the line numbers where that message occurred.

    The final JSON output now also includes the top-level error message and the "Caused by:" message,
    if available, under the keys "topError" and "cause".
    """
    try:
        cleaned_output = remove_gradle_footer(build_output)
    except Exception as e:
        logger.exception("Error during footer removal: %s", e)
        cleaned_output = build_output

    error_blocks = extract_error_blocks(cleaned_output)
    filtered_blocks = []
    for block in error_blocks:
        _, _, level, _ = extract_issue_details(block)
        if msg_type == "both" or (level == msg_type):
            filtered_blocks.append(block)
    # If no matching error blocks were found, fallback to using the entire cleaned output.
    if not filtered_blocks:
        filtered_blocks = [cleaned_output]

    formatted_blocks = [format_error_block(b, repo_root) for b in filtered_blocks]

    errors_by_category = {}
    examples_by_category = {}

    for block in formatted_blocks:
        filepath, line, level, message = extract_issue_details(block)
        if not filepath:
            category = "Raw Error"
            directory = "."
            filename = "raw_output.log"
            if category not in errors_by_category:
                errors_by_category[category] = {}
                examples_by_category[category] = Counter()
            if directory not in errors_by_category[category]:
                errors_by_category[category][directory] = {}
            if filename not in errors_by_category[category][directory]:
                errors_by_category[category][directory][filename] = []
            errors_by_category[category][directory][filename].append({"line": "", "message": block.strip()})
            examples_by_category[category][block.strip()] += 1
        else:
            category = categorize_issue(message, level)
            directory = os.path.dirname(filepath)
            filename = os.path.basename(filepath)

            if category not in errors_by_category:
                errors_by_category[category] = {}
                examples_by_category[category] = Counter()
            if directory not in errors_by_category[category]:
                errors_by_category[category][directory] = {}
            if filename not in errors_by_category[category][directory]:
                errors_by_category[category][directory][filename] = []
            errors_by_category[category][directory][filename].append({"line": line, "message": message})
            examples_by_category[category][message] += 1

    issues = []
    for cat, dir_dict in errors_by_category.items():
        total_count = sum(len(err_list) for d in dir_dict.values() for err_list in d.values())
        paths = []
        for directory, files_dict in dir_dict.items():
            files = []
            for fname, errors_list in files_dict.items():
                grouped_errors = {}
                for error in errors_list:
                    msg = error["message"]
                    grouped_errors.setdefault(msg, []).append(error["line"])
                formatted_errors = []
                for msg, lines in grouped_errors.items():
                    formatted_errors.append({"message": msg, "lines": lines})
                files.append({
                    "filename": fname,
                    "errors": formatted_errors
                })
            paths.append({
                "path": directory,
                "files": files
            })
        examples = [{"message": msg, "count": cnt}
                    for msg, cnt in examples_by_category[cat].most_common()]
        issues.append({
            "category": cat,
            "count": total_count,
            "paths": paths,
            "examples": examples
        })

    if GENERATE_SUMMARY:
        groups = defaultdict(lambda: {"count": 0, "locations": set(), "messages": Counter()})
        for block in formatted_blocks:
            filepath, line, level, message = extract_issue_details(block)
            if not filepath:
                continue
            cat = categorize_issue(message, level)
            groups[cat]["count"] += 1
            groups[cat]["locations"].add(filepath)
            groups[cat]["messages"][message] += 1
        summary = generate_summary(groups)
        general_line = extract_summary_line(cleaned_output, summary_marker)
        if general_line:
            summary += f"\n\nGeneral Summary: {general_line}"
    else:
        summary = extract_summary_line(cleaned_output, summary_marker)

    # Extract the top-level error message and cause from the original build output.
    top_error, cause = extract_top_level_error_and_cause(cleaned_output)

    result = {
        "issues": issues,
        "summary": mask_output(summary),
        "topError": top_error,
        "cause": cause
    }
    return json.dumps(result)
