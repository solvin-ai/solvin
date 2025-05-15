# tools/tool_ast_rewrite.py

"""
Rewrites code using user-specified search and replacement arguments.

Instead of requiring a multi-line semgrep rule string, the client now provides:
  1. search_pattern   (sets either the "pattern" or "pattern-regex" key, based on search_type)
  2. replace_pattern  (sets the "replace" key)
  3. search_type      (must be either "regex" or "ast")
  4. description      (optional; if provided this is used for the "message" key)
  5. languages        (optional; defaults to ["python"])
  6. target           (optional; defaults to the current directory ".")

The tool automatically generates a unique rule id and sets severity to INFO.

Before running this tool:
  - PyYAML must be installed (pip install pyyaml)
  - semgrep must be installed and in your PATH
"""

import os
import uuid
import tempfile
import subprocess
import yaml

from shared.config import config
from shared.logger import logger
from modules.tools_safety import get_repo_path, resolve_repo_path, check_path, mask_output


def tool_ast_rewrite(
    search_pattern: str,
    replace_pattern: str,
    search_type: str,
    target: str = ".",
    description: str = None,
    languages: list = None
) -> dict:
    # --- Sandbox safety: ensure REPO_NAME is set and target is inside that repo ---
    repo_name = config.get("REPO_NAME")
    if not repo_name:
        error_msg = "REPO_NAME not set in config."
        logger.error(error_msg)
        return {"success": False, "output": error_msg}

    try:
        repo_root = get_repo_path(repo_name)
    except Exception as exc:
        error_msg = f"Invalid repository root for '{repo_name}': {exc}"
        logger.error(error_msg)
        return {"success": False, "output": error_msg}

    try:
        safe_target = resolve_repo_path(repo_name, target)
    except Exception as exc:
        error_msg = f"Invalid target path '{target}': {exc}"
        logger.error(error_msg)
        return {"success": False, "output": error_msg}

    # enforce again for absolute paths
    safe_target = check_path(safe_target, allowed_root=repo_root)
    logger.debug(f"[tool_ast_rewrite] Safe target resolved to: {safe_target}")

    # Default languages
    if languages is None:
        languages = ["python"]

    # Validate search_type
    if search_type not in ("regex", "ast"):
        error_msg = "Invalid search_type. Must be either 'regex' or 'ast'."
        logger.error(error_msg)
        return {"success": False, "output": error_msg}

    # Build a unique semgrep rule
    rule_id = f"auto-{uuid.uuid4().hex}"
    message = description or "Automatic rewrite rule."
    rule = {
        "id": rule_id,
        "languages": languages,
        "severity": "INFO",
        "message": message,
        "replace": replace_pattern,
    }
    if search_type == "regex":
        rule["pattern-regex"] = search_pattern
    else:
        rule["pattern"] = search_pattern

    config_obj = {"rules": [rule]}

    # Write the rule to a temp file and run semgrep
    config_path = None
    try:
        yaml_text = yaml.safe_dump(config_obj, sort_keys=False)
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".yml", delete=False) as tmp:
            tmp.write(yaml_text)
            tmp.flush()
            config_path = tmp.name

        cmd = [
            "semgrep",
            "--config", config_path,
            "--metrics=off",
            "--autofix",
            safe_target
        ]
        logger.debug(f"[tool_ast_rewrite] Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        error_msg = "semgrep not found. Please install semgrep and ensure it is in your PATH."
        logger.exception(error_msg)
        return {"success": False, "output": error_msg}
    except Exception as exc:
        error_msg = f"Failed to run semgrep: {exc}"
        logger.exception(error_msg)
        return {"success": False, "output": error_msg}
    finally:
        if config_path and os.path.exists(config_path):
            try:
                os.remove(config_path)
            except Exception as cleanup_exc:
                logger.warning("Could not remove temp config %s: %s", config_path, cleanup_exc)

    # Check semgrep result
    if result.returncode != 0:
        stderr_masked = mask_output(result.stderr.strip())
        logger.error("Semgrep error: %s", stderr_masked)
        return {"success": False, "output": stderr_masked}

    stdout_masked = mask_output(result.stdout.strip() or "Semgrep rewrite applied successfully.")
    return {"success": True, "output": stdout_masked}


def get_tool() -> dict:
    """
    Returns the tool specification for invoking tool_ast_rewrite via the function interface.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_ast_rewrite",
            "description": (
                "Rewrites code across files using a search pattern and replace pattern. "
                "Use 'regex' search_type for pattern-regex or 'ast' for AST-based pattern."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search_pattern": {
                        "type": "string",
                        "description": (
                            "The code pattern for matching. For 'regex', e.g. "
                            "\"print\\s*\\((?P<args>.*)\\)\"; for 'ast', e.g. \"print($X)\"."
                        )
                    },
                    "replace_pattern": {
                        "type": "string",
                        "description": "The replacement pattern, e.g. \"logger.info($X)\"."
                    },
                    "search_type": {
                        "type": "string",
                        "enum": ["regex", "ast"],
                        "description": "Either 'regex' or 'ast'."
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description for the generated rule."
                    },
                    "languages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of languages (defaults to [\"python\"])."
                    },
                    "target": {
                        "type": "string",
                        "description": "File or directory to rewrite (defaults to \".\")."
                    }
                },
                "required": ["search_pattern", "replace_pattern", "search_type"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "mutating"
        }
    }


if __name__ == "__main__":
    # Example invocation
    example = tool_ast_rewrite(
        search_pattern="print($X)",
        replace_pattern="logger.info($X)",
        search_type="ast",
        target=".",
        description="Replace print with logger.info",
        languages=["python"]
    )
    print(example)
