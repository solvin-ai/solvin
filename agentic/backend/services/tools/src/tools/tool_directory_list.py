# tools/tool_directory_list.py

import os
from modules.tools_safety import get_safe_repo_root, resolve_safe_repo_path, check_path
from shared.logger import logger
import pathspec


def load_gitignore_spec(starting_path):
    """
    Traverse up from starting_path to locate a .gitignore file,
    stopping at the repository root.
    """
    current = os.path.abspath(starting_path)
    root_limit = os.path.abspath(get_safe_repo_root())
    gitignore_path = None

    while True:
        candidate = os.path.join(current, ".gitignore")
        if os.path.isfile(candidate):
            gitignore_path = candidate
            break
        if current == root_limit or current == os.path.dirname(current):
            break
        current = os.path.dirname(current)

    if gitignore_path:
        with open(gitignore_path, "r") as f:
            lines = f.read().splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    else:
        return pathspec.PathSpec.from_lines("gitwildmatch", [])


def build_tree(paths):
    """
    Given a list of relative file paths, build a nested list tree:
      [ "dir", [ ...subdirs and files... ], "file1", "file2", ... ]
    """
    tree = {}
    for rel_path in paths:
        parts = rel_path.split(os.sep)
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault("__files__", []).append(parts[-1])

    def dict_to_nested_list(name, subtree):
        dirs = []
        files = []
        if "__files__" in subtree:
            files.extend(sorted(subtree["__files__"]))
        for key, subtree_value in sorted(subtree.items()):
            if key == "__files__":
                continue
            child = dict_to_nested_list(key, subtree_value)
            if child:
                dirs.append(child)
        if not dirs and not files:
            return None
        if name:
            return [name, dirs + files]
        else:
            return dirs + files

    result = dict_to_nested_list("", tree)
    return result if result is not None else []


def tool_directory_list(extensions: list = None, path: str = ".") -> dict:
    """
    Lists files as a nested directory tree, filtered by extensions,
    pruning empty directories, ignoring files in .gitignore (if present),
    and also ignoring *.log, *.bak files and __pycache__ directories.
    """
    try:
        # Verify repository root exists and is safe
        repo_root = get_safe_repo_root()

        # Disallow absolute user paths
        if os.path.isabs(path):
            raise Exception("Absolute paths are not allowed. Please provide a relative path.")

        # Resolve the base directory inside the repo
        safe_base = resolve_safe_repo_path(path)

        # Load .gitignore from the nearest parent (if any)
        gitignore_spec = load_gitignore_spec(safe_base)

        # Built-in ignore patterns
        ignore_patterns = ["*.log", "*.bak"]

        matched_files = []
        for root, dirs, files in os.walk(safe_base):
            # Drop __pycache__ dirs
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            rel_dir = os.path.relpath(root, safe_base)
            if rel_dir == ".":
                rel_dir = ""

            for filename in files:
                # Built-in ignores
                if any(filename.lower().endswith(pat[1:]) for pat in ignore_patterns):
                    continue

                # .gitignore check (POSIX style)
                rel_file = os.path.join(rel_dir, filename) if rel_dir else filename
                if gitignore_spec.match_file(rel_file.replace(os.sep, "/")):
                    continue

                # Extension filtering
                exts = extensions if extensions is not None else [".java", ".py"]
                if not any(filename.lower().endswith(ext.lower()) for ext in exts):
                    continue

                full_path = os.path.join(root, filename)
                try:
                    # Final safety check
                    safe_full_path = check_path(full_path, allowed_root=repo_root)
                    rel_path = os.path.relpath(safe_full_path, safe_base)
                    matched_files.append(rel_path)
                except Exception:
                    # Skip anything that fails the safety check
                    continue

        tree_result = build_tree(matched_files)
        return {"success": True, "output": tree_result}

    except Exception as e:
        logger.error("Error in tool_directory_list: %s", str(e))
        return {"success": False, "output": str(e)}


def get_tool():
    """
    Returns the tool specification for directory listing.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_directory_list",
            "description": (
                "Lists files as a nested directory tree, showing only files in allowed extensions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional file extensions to include; defaults to ['.java', '.py']."
                    },
                    "path": {
                        "type": "string",
                        "description": "Starting relative directory (default '.').",
                        "default": "."
                    }
                },
                "required": [],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "readonly"
        }
    }
