# tools/tool_share_thoughts.py

import os
import time
from datetime import datetime

from shared.logger import logger
from shared.config import config
from modules.slack_integration import (
    slack_enabled,
    sync_client,
    post_message,
    post_and_wait
)
from modules.tools_safety import (
    get_safe_repo_root,
    get_log_dir,
    check_path,
    mask_output,
)
from slack_sdk.errors import SlackApiError

# ─── Load SLACK_REPLY_TIMEOUT (seconds) ───────────────────────────────────────
_raw = config.get("SLACK_REPLY_TIMEOUT", None)
try:
    SLACK_REPLY_TIMEOUT = int(_raw) if _raw is not None else 1200
except (TypeError, ValueError):
    logger.warning("Invalid SLACK_REPLY_TIMEOUT=%r; defaulting to 1200s", _raw)
    SLACK_REPLY_TIMEOUT = 1200

POLL_INTERVAL = 2.0  # seconds between Slack polls (unused when using post_and_wait)


def tool_share_thoughts(
    text: str,
    ask_user_input: bool = False
) -> dict:
    """
    1) Logs your thought locally.
    2) Always posts to your Slack target (if enabled).
    3) If ask_user_input=True, blocks up to SLACK_REPLY_TIMEOUT seconds
       waiting for the first thread‐reply, then records and closes the thread.
    Returns: {success, output, reply}
      - reply: the user’s reply text or None (on timeout/never asked).
    """
    logger.info("🔧 tool_share_thoughts called (ask_user_input=%s)", ask_user_input)

    try:
        # ─── 1) Local file prep ─────────────────────────────────────────────
        repo_root    = get_safe_repo_root()
        repo_name    = os.path.basename(repo_root)
        log_root     = check_path(get_log_dir(), allowed_root=get_log_dir())
        thoughts_dir = check_path(os.path.join(log_root, "thoughts"),
                                  allowed_root=log_root)
        os.makedirs(thoughts_dir, exist_ok=True)

        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{repo_name}_{ts}.txt"
        fpath = check_path(os.path.join(thoughts_dir, fname),
                           allowed_root=log_root)

        with open(fpath, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {text.strip()}\n")
        logger.info("  • Wrote thought to %s", fpath)

        # ─── Prepare Slack blocks with context header ─────────────────────────
        header_txt = f":thought_balloon: [{repo_name}]"
        try:
            issue_title = config.get("METADATA", {}).get("issue_title")
        except Exception:
            issue_title = None
        if issue_title:
            header_txt += f" - {issue_title}"

        slack_blocks = [
            {"type": "header",  "text": {"type": "plain_text", "text": header_txt}},
            {"type": "section", "text": {"type": "mrkdwn",       "text": text.strip()}},
        ]
        if ask_user_input:
            slack_blocks.append(
                {"type": "context", "elements": [
                    {"type": "mrkdwn", "text": "Reply in this thread and I'll record it."}
                ]}
            )

        # ─── 2) Post to Slack ────────────────────────────────────────────────
        if slack_enabled and sync_client:
            if ask_user_input:
                logger.info("  • Posting to Slack and waiting for a reply…")
                resp, reply = post_and_wait(
                    text=text.strip(),
                    blocks=slack_blocks,
                    fpath=fpath,
                    timeout=SLACK_REPLY_TIMEOUT
                )
                if reply:
                    output = f"Reply recorded: {reply}"
                else:
                    output = "[timeout waiting for Slack reply]"
                return {"success": True, "output": output, "reply": reply}

            else:
                logger.info("  • Posting to Slack (no reply requested)…")
                try:
                    resp = post_message(
                        text=text.strip(),
                        blocks=slack_blocks
                    )
                    ts2 = resp.get("ts")
                    output = f"Thought logged locally; posted to Slack (ts={ts2})."
                except SlackApiError as e:
                    logger.error("  • Failed to post to Slack: %s", e)
                    output = "Thought logged locally; [error posting to Slack]"
                return {"success": True, "output": output, "reply": None}

        else:
            logger.info("  • Slack integration disabled or client missing, skipping post")
            if ask_user_input:
                output = "[slack integration disabled]"
                return {"success": True, "output": output, "reply": None}
            else:
                output = "Thought logged locally."
                return {"success": True, "output": output, "reply": None}

    except Exception as e:
        logger.exception("tool_share_thoughts failed")
        return {"success": False, "output": mask_output(str(e)), "reply": None}


def get_tool():
    return {
        "type": "function",
        "function": {
            "name": "tool_share_thoughts",
            "description": (
                "Logs your thoughts, and only if ask_user_input=True, "
                "also blocks until you get a reply back from the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The thought to be shared."
                    },
                    "ask_user_input": {
                        "type": "boolean",
                        "description": "When true, wait for a user reply and return it.",
                        "default": False
                    }
                },
                "required": ["text"],
                "additionalProperties": False
            }
        },
        "internal": {
            "preservation_policy": "always",
            "type": "readonly"
        }
    }
