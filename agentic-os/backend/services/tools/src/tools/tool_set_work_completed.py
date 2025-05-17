# tools/tool_set_work_completed.py

import os
from shared.config import config
from shared.logger import logger
from modules.tools_safety import get_log_dir, check_path, mask_output
from modules.slack_integration import slack_enabled, post_message

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
        # 1) Write the report to disk
        with open(report_file_path, "w", encoding="utf-8") as f:
            f.write(report)
        safe_report_path = mask_output(report_file_path)
        summary = f"Report written to {safe_report_path}. Work declared as complete."

        logger.info(summary)

        # 2) Send to Slack: summary + full report text
        if slack_enabled:
            try:
                # wrap the report in a triple‐backtick code‐block so it’s easy to read
                slack_text = (
                    f":white_check_mark: {summary}\n\n"
                    "```"
                    f"{report}"
                    "```"
                )
                post_message(text=slack_text)
            except Exception as e:
                logger.error("Failed to post report to Slack: %s", e)

        # Return success, summary, and original report
        return {
            "success": True,
            "output": summary,
            "report": report
        }

    except Exception as e:
        safe_report_path = mask_output(report_file_path)
        err_message = f"Failed to write report to {safe_report_path}: {e}"
        logger.warning(err_message)

        if slack_enabled:
            try:
                post_message(text=f":warning: {err_message}")
            except Exception:
                pass

        # Return failure, error message, and original report
        return {
            "success": False,
            "output": err_message,
            "report": report
        }


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
