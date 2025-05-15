# tools/tool_replace_function_in_file.py

from shared.config import config
from modules.tools_safety import get_repo_path, resolve_repo_path, check_path, mask_output
import os
import modules.tools_replace_function_in_file_java as java
import modules.tools_replace_function_in_file_python as python


def tool_replace_function_in_file(file_path: str, function_text: str, fuzzy_match: bool = True) -> dict:
    """
    Replaces a function in the specified file by routing the request based on the file extension.

    For Java files (.java), the function in replace_function_in_file_java is called.
    For Python files (.py), the function in replace_function_in_file_python is called.

    Args:
        file_path (str): The path to the file where the function is to be replaced.
        function_text (str): The complete new function text (signature and body).
        fuzzy_match (bool): Whether to perform fuzzy matching for function detection (default: True).

    Returns:
        dict: A dictionary with "success" flag and "output" message.
    """
    # sandbox safety
    repo = config["REPO_NAME"]
    repo_root = get_repo_path(repo)
    safe_fp = resolve_repo_path(repo, file_path)
    safe_fp = check_path(safe_fp, allowed_root=repo_root)

    ext = os.path.splitext(safe_fp)[1].lower()
    if ext == ".java":
        result = java.tool_replace_function_in_file(safe_fp, function_text, fuzzy_match)
    elif ext == ".py":
        result = python.tool_replace_function_in_file(safe_fp, function_text, fuzzy_match)
    else:
        return {
            "success": False,
            "output": f"Unsupported file extension '{ext}' for file: {file_path}"
        }

    # scrub any absolute container paths out of the output
    if "output" in result and isinstance(result["output"], str):
        result["output"] = mask_output(result["output"])
    return result


def get_tool():
    """
    Returns the tool specification.
    """
    return {
        "type": "function",
        "function": {
            "name": "tool_replace_function_in_file",
            "description": (
                "Replaces a function in the specified file by routing the request based on the file extension. "
                "Calls the language-specific implementation for Java or Python as appropriate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file to update."
                    },
                    "function_text": {
                        "type": "string",
                        "description": (
                            "The complete new function text (signature/header and body). "
                            "For Java, its declared header must match the function in the file (ignoring annotations and whitespace). "
                            "For Python, it should similarly match the function definition."
                        )
                    },
                    "fuzzy_match": {
                        "type": "boolean",
                        "description": "If true, use fuzzy matching to find the function (default: true).",
                        "default": True
                    }
                },
                "required": ["file_path", "function_text"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "until-build",
            "type": "mutating"
        }
    }
