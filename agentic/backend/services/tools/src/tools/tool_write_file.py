# tools/tool_write_file.py

import os
import shutil
from shared.logger import logger
from modules.tools_safety import (
    get_safe_repo_root,
    resolve_safe_repo_path,
    mask_output,
)

def tool_write_file(file_path: str, new_content: str, create: bool = False) -> dict:
    """
    Overwrites or creates a file under the configured REPO_NAME repository:
    
    - create=True:
        • Fails if the target file already exists.
        • If it does not exist, creates any missing parent directories and writes the file.
    - create=False:
        • Fails if the target file does not exist.
        • If it exists, first makes a backup at `<file>.last`, then overwrites it.

    Args:
        file_path (str): Relative path to the file to update or create.
        new_content (str): New content to write.
        create (bool): If true, only create a new file (failing if it exists).
                       If false, only overwrite an existing file (failing if it does not exist).

    Returns:
        dict: {"success": True, "output": updated_file_content} on success,
              {"success": False, "output": error_message} on failure.
    """
    try:
        # 1) Establish and validate the repo root, then resolve our target path
        repo_root = get_safe_repo_root()
        safe_path = resolve_safe_repo_path(file_path)

        # 2) Ensure parent directory exists (or create if requested)
        parent = os.path.dirname(safe_path)
        if parent and not os.path.isdir(parent):
            if create:
                os.makedirs(parent, exist_ok=True)
                logger.debug(f"[tool_write_file] Created directory '{parent}'")
            else:
                return {
                    "success": False,
                    "output": mask_output(
                        f"The directory for file '{safe_path}' does not exist. "
                        "Set create=True to create it automatically."
                    )
                }

        exists = os.path.exists(safe_path)

        # 3) Enforce create vs overwrite semantics
        if create and exists:
            return {
                "success": False,
                "output": mask_output(
                    f"File '{safe_path}' already exists. Cannot override when create=True."
                )
            }
        if not create and not exists:
            return {
                "success": False,
                "output": mask_output(
                    f"File '{safe_path}' does not exist. Cannot overwrite when create=False."
                )
            }

        # 4) If overwriting, make a `.last` backup
        if not create and exists:
            backup = resolve_safe_repo_path(file_path + ".last")
            shutil.copy(safe_path, backup)
            logger.debug(f"[tool_write_file] Backed up '{safe_path}' to '{backup}'")

        # 5) Write the new content, then read it back
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        with open(safe_path, "r", encoding="utf-8") as f:
            updated = f.read()

        return {"success": True, "output": updated}

    except Exception as e:
        err = mask_output(f"An unexpected error occurred: {e}")
        logger.warning(err)
        return {"success": False, "output": err}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_write_file",
            "description": tool_write_file.__doc__,
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file to update or create."
                    },
                    "new_content": {
                        "type": "string",
                        "description": "New content to write."
                    },
                    "create": {
                        "type": "boolean",
                        "description": (
                            "If true, creates the file only if it does not already exist "
                            "(and creates missing directories). Fails if it exists. "
                            "If false, overwrites only if the file exists. Fails if it does not exist."
                        ),
                        "default": False
                    }
                },
                "required": ["file_path", "new_content"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "mutating"
        }
    }
