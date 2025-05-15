# tools/tool_directory_tree.py

"""
Generates a concise nested directory tree (directories only) as nested lists
while filtering out directories that do not contain any source code files.

Each qualifying directory is represented as:
    [directory_name, [child_directory_entries]] if it has qualifying children,
    or [directory_name] if it's a leaf node (contains source files but no qualifying children).
A directory is included in the output only if it contains at least one source code file
(with an allowed extension) OR if one (or more) of its subdirectories qualifies.
"""

import os
from shared.logger import logger
from modules.tools_safety import (
    get_safe_repo_root,
    resolve_safe_repo_path,
)

# Allowed source code file extensions
SOURCE_EXTENSIONS = {
    '.py', '.js', '.java', '.c', '.cpp', '.cs', '.rb',
    '.go', '.ts', '.jsx', '.tsx', '.sh', '.rs', '.swift',
    '.kt', '.m', '.scala', '.php', '.pl'
}

def is_source_file(filename: str) -> bool:
    """
    Returns True if the filename ends with one of the allowed source code extensions.
    """
    _, ext = os.path.splitext(filename)
    return ext.lower() in SOURCE_EXTENSIONS

def tool_directory_tree(path: str = ".", max_depth: int = 0, current_depth: int = 0) -> dict:
    """
    Recursively builds a directory tree as nested lists showing only those directories
    that contain source code files or have qualifying subdirectories.

    Args:
        path (str): Starting directory (default "."). If relative, it is resolved against
                    the current sandbox repositories root.
        max_depth (int): Maximum recursion depth (0 means no limit).
        current_depth (int): Current recursion depth (used internally).

    Returns:
        dict: Contains:
              - "success": Boolean indicating whether the tree was generated successfully.
              - "output": The nested directory tree structure as a list, or an error message.
                          Format: [dir_name, [children]] or [dir_name] for leaves.
                          Returns an empty list ([]) if the directory doesn't qualify.
    """
    try:
        # Top-level: reject absolute paths
        if current_depth == 0 and os.path.isabs(path):
            raise Exception("Absolute paths are not allowed. Please provide a relative path.")

        # Determine the safe starting path inside the repo
        if current_depth == 0 and path == ".":
            safe_path = get_safe_repo_root()
        else:
            # resolve_safe_repo_path handles both relative and absolute paths
            safe_path = resolve_safe_repo_path(path)

        children = []
        immediate_source_found = False

        # Traverse directory
        try:
            with os.scandir(safe_path) as iterator:
                for entry in iterator:
                    if entry.is_file():
                        if not immediate_source_found and is_source_file(entry.name):
                            immediate_source_found = True
                    elif entry.is_dir():
                        # Check depth limit before recursing
                        if max_depth == 0 or current_depth < max_depth:
                            # entry.path is absolute; recursive call will validate again
                            child_result = tool_directory_tree(entry.path, max_depth, current_depth + 1)
                            child_tree = child_result.get("output")
                            if child_tree:
                                children.append(child_tree)
        except OSError as e:
            logger.warning("Could not scan directory %s: %s", safe_path, e)
            # Treat as non-qualifying if unreadable, but don't fail
            return {"success": True, "output": []}

        # Build result if this directory qualifies
        result = []
        if immediate_source_found or children:
            dir_name = os.path.basename(safe_path) or safe_path
            if children:
                result = [dir_name, children]
            else:
                result = [dir_name]

        return {"success": True, "output": result}

    except Exception as ex:
        logger.error("Error generating directory tree for path '%s': %s", path, ex)
        return {"success": False, "output": str(ex)}

def get_tool():
    """
    Returns the tool specification for generating the filtered, concise directory tree.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_directory_tree",
            "description": (
                "Generates a nested directory tree (directories only) as nested arrays, "
                "including a directory only if it or one of its subdirectories contains a source code file. "
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative starting directory (default '.').",
                        "default": "."
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum recursion depth (0 means no limit).",
                        "default": 0
                    }
                },
                "required": [],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "one-of",
            "type": "readonly"
        }
    }
