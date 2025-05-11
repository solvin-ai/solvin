# modules/tools_replace_function_in_file_java.py

"""
Replaces in a given Java file the definition of a method (signature+body)
with new function text. This version scans anywhere in the file by recursing
through all type declarations. It now returns a dictionary containing a
boolean "success" flag.
"""

import os
import shutil
import re  # for regex processing
import javalang
from modules.tools_safety import check_path, get_sandbox_repo_root, mask_output
from modules.tools_safety import resolve_sandbox_path
from modules.logs import logger

def extract_function_text(content: str, start_index: int) -> str:
    """
    Uses a simple brace-matching algorithm starting at start_index in content.
    Returns the full text from start_index to the matching closing brace.
    """
    pos_brace = content.find('{', start_index)
    pos_semicolon = content.find(';', start_index)
    if pos_brace == -1 or (pos_semicolon != -1 and pos_semicolon < pos_brace):
        end_offset = pos_semicolon + 1 if pos_semicolon != -1 else len(content)
        return content[start_index:end_offset]
    # Now we have a brace; count braces until we close all.
    index = pos_brace
    count = 0
    while index < len(content):
        if content[index] == '{':
            count += 1
        elif content[index] == '}':
            count -= 1
            if count == 0:
                index += 1  # include the closing brace
                break
        index += 1
    return content[start_index:index]

def compute_method_signature(node) -> str:
    """
    Builds a string signature for a method or constructor from the AST node.
    For methods, includes modifiers, return type, name, and parameters.
    For constructors, includes modifiers, class name, and parameters.
    """
    modifier_str = " ".join(sorted(node.modifiers)) if node.modifiers else ""
    param_list = []
    for param in node.parameters:
        # Get parameter type name; include dimensions if present.
        type_name = param.type.name if hasattr(param.type, 'name') else str(param.type)
        if param.type.dimensions:
            type_name += "[]" * len(param.type.dimensions)
        param_list.append(f"{type_name} {param.name}")
    params = ", ".join(param_list)
    if hasattr(node, 'return_type') and node.return_type is not None:
        ret_type = node.return_type.name if hasattr(node.return_type, 'name') else str(node.return_type)
        signature = f"{modifier_str} {ret_type} {node.name}({params})".strip()
    else:
        # For constructors (or void methods as parsed by javalang).
        signature = f"{modifier_str} {node.name}({params})".strip()
    return signature

def compute_offset(content: str, position: tuple) -> int:
    """
    Converts a (line, column) tuple (1-indexed) from the AST node into a zero-indexed character offset.
    """
    lines = content.splitlines(keepends=True)
    line_no, col_no = position  # both 1-indexed from javalang
    offset = sum(len(lines[i]) for i in range(line_no - 1)) + (col_no - 1)
    return offset

def normalize_signature(sig: str) -> str:
    """
    Normalizes a signature string by collapsing multiple whitespace characters.
    Also reorders any recognized modifiers.
    """
    cleaned = " ".join(sig.split())
    valid_modifiers = {"public", "protected", "private", "static",
                       "abstract", "final", "synchronized", "native",
                       "strictfp", "default"}
    tokens = cleaned.split(" ")
    modifiers = []
    remainder = []
    for token in tokens:
        if token in valid_modifiers:
            modifiers.append(token)
        else:
            remainder.append(token)
    normalized_modifiers = " ".join(sorted(modifiers))
    normalized = (normalized_modifiers + " " if normalized_modifiers and remainder else "") + " ".join(remainder)
    return normalized.strip()

def scan_method_in_types(type_decl, candidate_signature: str, file_content: str, signatures_list: list) -> tuple:
    """
    Recursively scans a type declaration (and its inner types) for methods or constructors.
    For each method found, compute its normalized signature and compare it with candidate_signature.
    When a match is found, return a tuple: (start_offset, end_offset) for the method's definition.
    Accumulates all discovered signatures in signatures_list for logging.
    """
    if not hasattr(type_decl, 'body'):
        return None

    for member in type_decl.body:
        if isinstance(member, (javalang.tree.MethodDeclaration, javalang.tree.ConstructorDeclaration)):
            if not hasattr(member, 'position') or member.position is None:
                continue
            computed_sig = compute_method_signature(member)
            normalized_computed_sig = normalize_signature(computed_sig)
            signatures_list.append(normalized_computed_sig)
            logger.debug(f"AST Function: '{normalized_computed_sig}' at line {member.position[0]}, column {member.position[1]}")
            if normalized_computed_sig == candidate_signature:
                start_offset = compute_offset(file_content, member.position)
                extracted_text = extract_function_text(file_content, start_offset)
                return (start_offset, start_offset + len(extracted_text))
        elif isinstance(member, (javalang.tree.ClassDeclaration,
                                 javalang.tree.InterfaceDeclaration,
                                 javalang.tree.EnumDeclaration)):
            result = scan_method_in_types(member, candidate_signature, file_content, signatures_list)
            if result:
                return result
    return None

def tool_replace_function_in_file(file_path: str, function_text: str, fuzzy_match: bool = True) -> dict:
    """
    Replaces in the given Java source file the definition (declaration+body) of the method
    that matches the provided new function text. It uses a robust recursive approach:
      - Extracts the candidate signature from function_text by accumulating header lines
        (ignoring annotations, inline comments, and empty lines) until the '{'
      - Normalizes the candidate signature. (Adjusted to remove "void" and generics.)
      - Parses the source file with javalang.
      - Recursively scans all type declarations for a method/constructor with a normalized signature.
      - If a match is found, uses the computed AST position and a brace-matching algorithm to extract
        the old function text, and replaces it with function_text.
      - A backup (.last) is created before writing the changes.

    Args:
      file_path (str): Relative path to the Java file.
      function_text (str): The complete new function text (header and body).
      fuzzy_match (bool): If true, remove package qualifiers from type names for fuzzy matching (default: True).

    Returns:
      dict: {"success": boolean, "output": message} indicating success or failure.
    """
    logger.debug(f"[tool_replace_function_in_file] Current working directory before resolving file_path: '{os.getcwd()}'")
    safe_file_path = resolve_sandbox_path(file_path)
    logger.debug(f"[tool_replace_function_in_file] Resolved safe_file_path: '{safe_file_path}' with cwd: '{os.getcwd()}'")

    # Compute a relative file path based on the sandbox repository root for clearer messaging.
    repo_root = get_sandbox_repo_root()
    if safe_file_path.startswith(repo_root):
        masked_file_path = os.path.relpath(safe_file_path, repo_root)
    else:
        masked_file_path = mask_output(safe_file_path)

    directory = os.path.dirname(safe_file_path)
    if not os.path.isdir(directory):
        error_message = (f"The directory for file '{masked_file_path}' does not exist. "
                         "Please check the file path or create it.")
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
        tree = javalang.parse.parse(file_content)
    except Exception as e:
        error_message = f"Failed to parse Java file '{masked_file_path}': {e}"
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    # --- Candidate Signature Extraction: accumulate header lines until '{' ---------------------------
    candidate_lines = []
    for line in function_text.splitlines():
        stripped = line.strip()
        # Skip empty lines, annotations, inline comments, and block comment lines
        if (not stripped or
            stripped.startswith("@") or
            stripped.startswith("/**") or
            stripped.startswith("/*") or
            stripped.startswith("*") or
            stripped.startswith("*/") or
            stripped.startswith("//")):
            continue
        candidate_lines.append(stripped)
        if "{" in stripped:
            break
    if not candidate_lines:
        error_message = "Provided function text does not contain a valid signature header."
        logger.warning(error_message)
        return {"success": False, "output": error_message}
    header = " ".join(candidate_lines)
    candidate_signature = header.split("{")[0].strip()
    # Remove redundant "void" and generic type parameters.
    candidate_signature = re.sub(r'\bvoid\b', '', candidate_signature, count=1)
    candidate_signature = re.sub(r'<[^<>]+>', '', candidate_signature)
    candidate_signature = re.sub(r',\s*', ', ', candidate_signature)
    # Apply fuzzy matching if enabled: remove package qualifiers from type names.
    if fuzzy_match:
        candidate_signature = re.sub(r'\b(?:[a-zA-Z_]\w*\.)+', '', candidate_signature)
        logger.debug("Applied fuzzy match: removed package qualifiers from candidate signature.")
    normalized_candidate_sig = normalize_signature(candidate_signature)
    logger.debug(f"Normalized candidate signature: '{normalized_candidate_sig}'")
    # ---------------------------------------------------------------------------------------------

    # --- Simple text search for debugging purposes ------------------------------------------
    simple_index = file_content.find(candidate_signature)
    if simple_index != -1:
        simple_function_text = extract_function_text(file_content, simple_index)
        logger.debug("Simple text search found function text:\n" + simple_function_text.strip())
    else:
        logger.debug(f"Simple text search did not find '{candidate_signature}' in the file.")
    # ---------------------------------------------------------------------------------------------

    # --- Recursively scan the AST for our candidate method -------------------------------------
    ast_function_signatures = []  # accumulate discovered signatures
    found_region = None
    for type_decl in tree.types:
        found_region = scan_method_in_types(type_decl, normalized_candidate_sig, file_content, ast_function_signatures)
        if found_region:
            break
    logger.debug("All functions found in AST: " + ", ".join(ast_function_signatures))
    # ---------------------------------------------------------------------------------------------

    if not found_region:
        error_message = (f"Function with signature starting '{candidate_signature}' not found in '{masked_file_path}'.")
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    matching_start, matching_end = found_region

    # Replace the old function text with the new function_text.
    new_file_content = file_content[:matching_start] + function_text + file_content[matching_end:]

    try:
        backup_path = safe_file_path + ".last"
        logger.debug(f"[tool_replace_function_in_file] Current working directory before resolving backup_path: '{os.getcwd()}'")
        backup_path = resolve_sandbox_path(backup_path)
        logger.debug(f"[tool_replace_function_in_file] Resolved backup_path: '{backup_path}' with cwd: '{os.getcwd()}'")
        # Compute a relative backup path based on the sandbox repository root.
        repo_root_backup = get_sandbox_repo_root()
        if backup_path.startswith(repo_root_backup):
            masked_backup_path = os.path.relpath(backup_path, repo_root_backup)
        else:
            masked_backup_path = mask_output(backup_path)
        if not os.path.exists(backup_path):
            try:
                shutil.copy(safe_file_path, backup_path)
            except Exception as e:
                return {"success": False, "output": f"Failed to create backup for '{masked_backup_path}': {e}"}
    except Exception as e:
        error_message = f"Error during backup creation for '{masked_backup_path}': {e}"
        logger.warning(error_message)
        return {"success": False, "output": error_message}

    try:
        with open(safe_file_path, "w", encoding="utf-8") as f:
            f.write(new_file_content)
        logger.info(f"Successfully replaced function with signature '{normalized_candidate_sig}' in file '{masked_file_path}'.")
        return {"success": True, "output": f"Successfully replaced function with signature '{normalized_candidate_sig}' in file '{masked_file_path}'."}
    except Exception as e:
        error_message = f"An error occurred while writing to '{masked_file_path}': {e}"
        logger.warning(error_message)
        return {"success": False, "output": error_message}
