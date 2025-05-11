# tools/tool_replace_imports_in_file.py

from shared.config import config
from shared.logger import logger

from modules.tools_safety import get_repo_path, resolve_repo_path, mask_output

import os
import shutil
import re
import ast


def tool_replace_imports_in_file(file_path: str, imports_text: str) -> dict:
    # 1) Repository safety
    repo = config["REPO_NAME"]
    try:
        get_repo_path(repo)
    except Exception as e:
        msg = f"Invalid repository root for '{repo}': {e}"
        logger.warning(mask_output(msg))
        return {"success": False, "output": mask_output(msg)}

    try:
        safe_file_path = resolve_repo_path(repo, file_path)
    except Exception as e:
        msg = f"Access violation for file '{file_path}': {e}"
        logger.warning(mask_output(msg))
        return {"success": False, "output": mask_output(msg)}

    directory = os.path.dirname(safe_file_path)
    if not os.path.isdir(directory):
        msg = f"The directory for file '{mask_output(safe_file_path)}' does not exist."
        logger.warning(mask_output(msg))
        return {"success": False, "output": mask_output(msg)}

    try:
        with open(safe_file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
    except Exception as e:
        msg = f"Failed to read file '{mask_output(safe_file_path)}': {e}"
        logger.warning(mask_output(msg))
        return {"success": False, "output": mask_output(msg)}

    # Normalize imports_text to end with a newline
    if not imports_text.endswith("\n"):
        imports_text += "\n"

    ext = os.path.splitext(safe_file_path)[1].lower()
    lines = file_content.splitlines(keepends=True)
    new_file_content = None

    # 2) Python branch using ast
    if ext == ".py":
        try:
            tree = ast.parse(file_content)
            # Collect top‐level import nodes
            imports = [
                node for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))
            ]
            if imports:
                start = imports[0].lineno - 1
                # end_lineno is available in Python 3.8+
                end = imports[-1].end_lineno
            else:
                # Insert after module docstring if present
                if (
                    tree.body
                    and isinstance(tree.body[0], ast.Expr)
                    and isinstance(tree.body[0].value, ast.Constant)
                    and isinstance(tree.body[0].value.value, str)
                ):
                    start = end = tree.body[0].end_lineno
                else:
                    start = end = 0

            import_lines = imports_text.splitlines(keepends=True)
            new_lines = lines[:start] + import_lines + lines[end:]
            new_file_content = "".join(new_lines)

        except Exception:
            # On parse failure, prepend imports
            new_file_content = imports_text + file_content

    # 3) Java branch using javalang AST, fallback to regex
    else:
        # Attempt to use javalang
        use_regex = True
        try:
            import javalang
        except ImportError:
            use_regex = True
        else:
            try:
                tree = javalang.parse.parse(file_content)
                use_regex = False
            except Exception:
                use_regex = True

        if not use_regex:
            # AST‐based Java imports handling
            import_positions = [
                imp.position[0] for imp in tree.imports
                if getattr(imp, "position", None)
            ]
            if import_positions:
                start = min(import_positions) - 1
                end = max(import_positions)
            else:
                # Insert after package declaration if present
                if tree.package and getattr(tree.package, "position", None):
                    pkg_line = tree.package.position[0]
                    start = end = pkg_line
                else:
                    start = end = 0

            import_lines = imports_text.splitlines(keepends=True)
            new_lines = lines[:start] + import_lines + lines[end:]
            new_file_content = "".join(new_lines)

        else:
            # Fallback to regex for Java
            import_section = re.compile(
                r"(?P<imports>(?:^[ \t]*import\s.*?;\s*\n)+)", re.MULTILINE
            )
            package_section = re.compile(
                r"(?P<package>^[ \t]*package\s.*?;\s*\n)", re.MULTILINE
            )

            m = import_section.search(file_content)
            if m:
                s, e = m.start("imports"), m.end("imports")
                new_file_content = (
                    file_content[:s] + imports_text + file_content[e:]
                )
            else:
                m2 = package_section.search(file_content)
                if m2:
                    pos = m2.end("package")
                    new_file_content = (
                        file_content[:pos] + imports_text + file_content[pos:]
                    )
                else:
                    new_file_content = imports_text + file_content

    # 4) Backup and write
    backup_candidate = safe_file_path + ".last"
    try:
        backup_path = resolve_repo_path(repo, backup_candidate)
    except Exception as e:
        msg = f"Error during backup resolution for '{mask_output(safe_file_path)}': {e}"
        logger.warning(mask_output(msg))
        return {"success": False, "output": mask_output(msg)}

    if not os.path.exists(backup_path):
        try:
            shutil.copy(safe_file_path, backup_path)
        except Exception as e:
            msg = f"Failed to create backup for '{mask_output(safe_file_path)}': {e}"
            logger.warning(mask_output(msg))
            return {"success": False, "output": mask_output(msg)}

    try:
        with open(safe_file_path, "w", encoding="utf-8") as f:
            f.write(new_file_content)
        msg = f"Successfully replaced the imports section in '{mask_output(safe_file_path)}'."
        logger.info(msg)
        return {"success": True, "output": mask_output(msg)}
    except Exception as e:
        msg = f"An error occurred while writing to '{mask_output(safe_file_path)}': {e}"
        logger.warning(mask_output(msg))
        return {"success": False, "output": mask_output(msg)}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_replace_imports_in_file",
            "description": (
                "Replaces in the specified Java or Python file the imports section "
                "with the provided new imports text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file to update.",
                    },
                    "imports_text": {
                        "type": "string",
                        "description": (
                            "The new imports section text. For Java, each statement "
                            "must end with a semicolon; for Python, standard `import` "
                            "and `from … import …` lines."
                        ),
                    },
                },
                "required": ["file_path", "imports_text"],
                "additionalProperties": False,
                "strict": True,
            },
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "mutating",
        },
    }
