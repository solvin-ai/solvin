# modules/tools_replace_function_in_file_python.py

"""
Replaces in a given Python file the definition of a function (signature+body)
with new function text. Returns a dictionary containing a boolean "success" flag.
"""

import os
import shutil
import re
import ast

from shared.config import config
from modules.tools_safety import mask_output, resolve_repo_path, get_repo_path
from shared.logger import logger

def compute_function_signature(node) -> str:
    """
    Builds a string signature for a function from the AST node.
    Includes the function name and its parameter names.
    """
    args = []
    for arg in node.args.args:
        args.append(arg.arg)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    for arg in node.args.kwonlyargs:
        args.append(arg.arg)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    signature = f"def {node.name}(" + ", ".join(args) + ")"
    return signature

def normalize_signature(sig: str) -> str:
    """
    Normalizes a signature string by collapsing multiple whitespace characters.
    """
    return " ".join(sig.split())

def get_node_offsets(content: str, node) -> tuple:
    """
    Computes the start and end character offsets for the AST node in the given content.
    Uses the node's lineno and end_lineno values.
    """
    lines = content.splitlines(keepends=True)
    start_offset = sum(len(lines[i]) for i in range(node.lineno - 1))
    if hasattr(node, "end_lineno") and node.end_lineno is not None:
        end_offset = sum(len(lines[i]) for i in range(node.end_lineno))
    else:
        end_offset = len(content)
    return start_offset, end_offset

def extract_candidate_signature(function_text: str) -> str:
    """
    Extracts the candidate function signature from the provided function text.
    Accumulates lines (skipping comments and decorator lines) starting from the first
    line that begins with 'def ' until a line ending with ':' is encountered.
    """
    candidate_lines = []
    lines = function_text.splitlines()
    collecting = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if stripped.startswith("def "):
            collecting = True
            candidate_lines.append(stripped)
            if stripped.endswith(":"):
                break
            continue
        if collecting:
            candidate_lines.append(stripped)
            if stripped.endswith(":"):
                break
    if not candidate_lines:
        raise ValueError("Provided function text does not contain a valid signature header.")
    candidate_header = " ".join(candidate_lines)
    if candidate_header.endswith(":"):
        candidate_header = candidate_header[:-1].strip()
    return candidate_header

def tool_replace_function_in_file(file_path: str, function_text: str, fuzzy_match: bool = True) -> dict:
    """
    Replaces in the given Python source file the definition (declaration+body) of the function
    that matches the provided new function text. The process is as follows:
      - Extracts the candidate signature from function_text.
      - Normalizes the candidate signature.
      - Parses the source file using the ast module.
      - Traverses the AST to locate a function definition with a matching normalized signature.
      - If found, computes character offsets for the function definition, creates a backup (.last),
        and replaces the function text.

    Args:
      file_path (str): Path to the Python file, relative to the repo root.
      function_text (str): The complete new function text (signature and body).
      fuzzy_match (bool): If true, use fuzzy matching for signatures (default: True).

    Returns:
      dict: {"success": boolean, "output": message} indicating success or failure.
    """
    # Determine which repo we're operating in
    try:
        repo_name = config.get("REPO_NAME")
        if not repo_name:
            raise RuntimeError("REPO_NAME must be set in config to the active repository name.")
        # Resolve the user-supplied path inside that repo
        safe_file_path = resolve_repo_path(repo_name, file_path)
    except Exception as e:
        error_message = f"Error resolving file path '{file_path}': {e}"
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    # For messages, compute a path relative to the repo root if possible
    repo_root = get_repo_path(repo_name)
    if safe_file_path.startswith(repo_root + os.sep) or safe_file_path == repo_root:
        masked_file_path = os.path.relpath(safe_file_path, repo_root)
    else:
        masked_file_path = mask_output(safe_file_path)

    directory = os.path.dirname(safe_file_path)
    if not os.path.isdir(directory):
        error_message = (
            f"The directory for file '{masked_file_path}' does not exist. "
            "Please check the file path or create it."
        )
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    try:
        with open(safe_file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
    except Exception as e:
        error_message = f"Failed to read file '{masked_file_path}': {e}"
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    try:
        tree = ast.parse(file_content)
    except Exception as e:
        error_message = f"Failed to parse Python file '{masked_file_path}': {e}"
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    try:
        candidate_signature = extract_candidate_signature(function_text)
    except ValueError as ve:
        error_message = str(ve)
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    normalized_candidate_sig = normalize_signature(candidate_signature)
    logger.debug(f"Normalized candidate signature: '{normalized_candidate_sig}'")

    found_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            computed_sig = compute_function_signature(node)
            normalized_computed_sig = normalize_signature(computed_sig)
            logger.debug(f"AST Function: '{normalized_computed_sig}' at line {node.lineno}")
            if normalized_computed_sig == normalized_candidate_sig:
                found_node = node
                break

    if not found_node:
        error_message = (
            f"Function with signature '{candidate_signature}' not found in '{masked_file_path}'."
        )
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    start_offset, end_offset = get_node_offsets(file_content, found_node)
    new_file_content = file_content[:start_offset] + function_text + file_content[end_offset:]

    # Create a backup before overwriting
    try:
        backup_path = safe_file_path + ".last"
        # Re-validate the backup path stays inside the same repo
        backup_path = resolve_repo_path(repo_name, backup_path)
        if backup_path.startswith(repo_root + os.sep) or backup_path == repo_root:
            masked_backup_path = os.path.relpath(backup_path, repo_root)
        else:
            masked_backup_path = mask_output(backup_path)
        if not os.path.exists(backup_path):
            shutil.copy(safe_file_path, backup_path)
    except Exception as e:
        error_message = f"Failed to create backup for '{masked_backup_path}': {e}"
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    # Write out the updated file
    try:
        with open(safe_file_path, "w", encoding="utf-8") as f:
            f.write(new_file_content)
        success_message = (
            f"Successfully replaced function with signature '{normalized_candidate_sig}' "
            f"in file '{masked_file_path}'."
        )
        logger.info(success_message)
        return {"success": True, "output": success_message}
    except Exception as e:
        error_message = f"An error occurred while writing to '{masked_file_path}': {e}"
        logger.warning(error_message)
        return {"success": False, "output": error_message}
