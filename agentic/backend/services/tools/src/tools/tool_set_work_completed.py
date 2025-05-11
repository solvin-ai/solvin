# tools/tool_set_work_completed.py

from shared.config import config
from modules.tools_safety import get_log_dir, check_path, mask_output
import os
from shared.logger import logger


def tool_set_work_completed(report: str = None) -> dict:
    if report is None:
        raise Exception("`report` parameter is required.")

    # Prepare logs directory
    logs_dir = get_log_dir()
    os.makedirs(logs_dir, exist_ok=True)

    # Determine report file path under the logs directory
    repo_name = config.get("REPO_NAME", "unknown_repo")
    report_file_path = os.path.join(logs_dir, f"{repo_name}_report.log")
    report_file_path = check_path(report_file_path, allowed_root=logs_dir)

    try:
        with open(report_file_path, "w", encoding="utf-8") as f:
            f.write(report)
        safe_report_path = mask_output(report_file_path)
        message = f"Report written to {safe_report_path}. Work declared as complete."
        logger.info(message)
        return {"success": True, "output": message}
    except Exception as e:
        safe_report_path = mask_output(report_file_path)
        err_message = f"Failed to write report to {safe_report_path}: {e}"
        logger.warning(err_message)
        return {"success": False, "output": err_message}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_set_work_completed",
            "description": (
                "Marks final work completion only after a full successful build and test cycles. "
                "This tool must ONLY be used after all issues are fixed, the project built successfully, "
                "and all tests passed. Do not use it for general reporting or intermediate status updates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "report": {
                        "type": "string",
                        "description": (
                            "The final summary report confirming that work is complete, "
                            "the project has built successfully, and all tests have passed."
                        )
                    }
                },
                "required": ["report"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "one-of",
            "type": "readonly"
        }
    }
