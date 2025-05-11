# tools/tool_share_thoughts.py

"""
Shares your thoughts regarding issues, problems, or inquiries related to builds and source code.
If 'ask_user_input' is True, a follow-up prompt allows for additional input.
"""

import os
from datetime import datetime

from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings

from shared.config import config
from shared.logger import logger

from modules.tools_safety import (
    get_safe_repo_root,
    get_log_dir,
    check_path,
    mask_output,
)

def prompt_continuation(width, line_number, wrap_count):
    if wrap_count > 0:
        return " " * (width - 3) + "-> "
    else:
        text = ("- %i - " % (line_number + 1)).rjust(width)
        return text

bindings = KeyBindings()

@bindings.add("escape", "enter", eager=True)
def _(event):
    event.current_buffer.validate_and_handle()

@bindings.add("c-d", eager=True)
def _(event):
    event.current_buffer.validate_and_handle()

@bindings.add("f2", eager=True)
def _(event):
    event.current_buffer.validate_and_handle()


def tool_share_thoughts(text: str, ask_user_input: bool = False) -> dict:
    logger.info(f"Sharing thoughts: {text!r}")
    try:
        # 1) Ensure our repo is configured and valid
        repo_root = get_safe_repo_root()
        repo_name = os.path.basename(repo_root)

        # 2) Prepare the 'thoughts' directory under logs/
        log_root = get_log_dir()
        log_root = check_path(log_root, allowed_root=log_root)

        thoughts_dir = os.path.join(log_root, "thoughts")
        thoughts_dir = check_path(thoughts_dir, allowed_root=log_root)
        os.makedirs(thoughts_dir, exist_ok=True)

        # 3) Create & check the thought_file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{repo_name}_{timestamp}.txt"
        thought_file = os.path.join(thoughts_dir, filename)
        thought_file = check_path(thought_file, allowed_root=log_root)

        # 4) Write the thought (and optional reply)
        user_reply = ""
        with open(thought_file, "a", encoding="utf-8") as f:
            f.write(f"Thought at {timestamp}: {text.strip()}\n")

            if ask_user_input:
                followup = (
                    "\nWe'd love to hear more!  "
                    "Finish with Ctrl-D (Unix) or Ctrl-Z (Windows), or press Meta+Enter / F2:\n"
                )
                user_reply = prompt(
                    followup,
                    multiline=True,
                    key_bindings=bindings,
                    prompt_continuation=prompt_continuation,
                ).strip()
                reply_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                f.write(f"Reply at {reply_ts}: {user_reply}\n")

        msg = "Thought shared successfully."
        if ask_user_input:
            msg += f" Your reply was recorded as: '{user_reply}'"
        return {"success": True, "output": msg}

    except Exception as e:
        logger.exception("Error sharing thoughts")
        return {"success": False, "output": mask_output(str(e))}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_share_thoughts",
            "description": (
                "Shares your thoughts regarding issues, problems, or inquiries related to builds and source code. "
                "If 'ask_user_input' is True, a follow‐up prompt allows for additional input."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The thoughts to be shared."
                    },
                    "ask_user_input": {
                        "type": "boolean",
                        "description": "Set to True if you want to prompt for an additional reply.",
                        "default": False
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
                "strict": True
            }
        },
        "internal": {
            "preservation_policy": "always",
            "type": "readonly"
        }
    }
