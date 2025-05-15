# tools/tool_find_files.py

import os

from shared.logger import logger
logger = logger

from modules.tools_safety import resolve_safe_repo_path, mask_output
from modules.tools_utils import group_paths

def tool_find_files(files: list) -> dict:
    """
    Searches for files with the given names within each file-object’s specified search directory.

    Args:
        files (list): An array of dicts. Each dict must have a "filename" key and may
                      optionally have a "file_path" key specifying the starting directory to search
                      (relative to the current repo root; defaults to ".").

    Returns:
        dict: {
            "success": True,
            "output": {
                "found":   a nested, compressed array of found file paths (masked),
                "not_found": a list of filenames that were not found
            }
        }
    """
    if files is None:
        raise Exception("files parameter is required.")
    if not isinstance(files, list):
        raise Exception("files parameter must be a list of objects (each with a 'filename' key).")

    found_paths = []
    not_found = []

    for file_obj in files:
        if not isinstance(file_obj, dict):
            raise Exception(
                "Each element in files must be an object/dict with keys 'filename' and optional 'file_path'."
            )
        if "filename" not in file_obj:
            raise Exception("Each file object must have a 'filename' key.")

        filename = file_obj["filename"]
        raw_base_path = file_obj.get("file_path", ".")

        logger.debug(
            f"[tool_find_files] Before resolving base_path: raw_base_path='{raw_base_path}', cwd='{os.getcwd()}'"
        )

        # Resolve and sanitize the base path within the repository
        safe_base_path = resolve_safe_repo_path(raw_base_path)
        logger.debug(
            f"[tool_find_files] After resolving base_path: safe_base_path='{safe_base_path}', cwd='{os.getcwd()}'"
        )

        logger.debug(
            f"[tool_find_files] Preparing to walk directory: '{safe_base_path}' with followlinks=True, cwd='{os.getcwd()}'"
        )

        found = None

        # Walk the directory tree starting at safe_base_path
        for root, dirs, files_in_dir in os.walk(safe_base_path, followlinks=True):
            if filename in files_in_dir:
                full_path = os.path.join(root, filename)
                logger.debug(
                    f"[tool_find_files] Found candidate file path: '{full_path}', cwd='{os.getcwd()}'"
                )

                # Sanitize the found file path
                safe_found_path = resolve_safe_repo_path(full_path)
                logger.debug(
                    f"[tool_find_files] Resolved found file path to '{safe_found_path}', cwd='{os.getcwd()}'"
                )

                found = mask_output(safe_found_path)
                break

        if found is not None:
            found_paths.append(found)
        else:
            not_found.append(filename)

    grouped_found = group_paths(found_paths) if found_paths else []
    return {"success": True, "output": {"found": grouped_found, "not_found": not_found}}


def get_tool():
    """
    Returns the tool specification for finding files.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_find_files",
            "description": (
                "Finds files by name within a directory tree. Input is an array of objects with keys "
                "'filename' and an optional relative 'file_path'. "
                "Returns found paths as a nested, compressed array and a list of filenames not found."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": (
                            "Array of objects, each with a 'filename' property and an optional 'file_path' specifying "
                            "the relative starting directory (defaults to '.')."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string", "description": "Name of the file to find."},
                                "file_path": {"type": "string", "description": "Starting directory to search (optional)."}
                            },
                            "required": ["filename"],
                            "additionalProperties": False,
                            "strict": True
                        }
                    }
                },
                "required": ["files"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "readonly"
        }
    }
