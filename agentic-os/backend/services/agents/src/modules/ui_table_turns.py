# modules/ui_table_turns.py

"""
Overview:
  • This module prints a summary turns table for conversation history (excluding turn 0).
  • It retrieves conversation history from modules.turns_list.
  • The table displays the following columns:
         Del | T # | Tool | Policy | KB I/O | Status | Args Hash | Secs | Reason | Purge | Filename / Input Args
  • For each turn the first message is used to aggregate metadata.
  • The dynamic column ("Filename / Input Args") is smart truncated based on the available space,
    which is calculated using centralized helpers in ui_tables_common.

Usage:
  • Calling print_turns_table() prints the table to the terminal.
"""

import os
from pprint import pformat

from modules.unified_turn import UnifiedTurn, StrictDict
from modules.turns_list import get_turns_list
from modules.agent_context import get_current_agent
from shared.config import config

# Import centralized Rich table helpers.
from modules.ui_tables_common import (
    get_console,
    create_rich_table,
    smart_truncate_text,
    compute_dynamic_column_width,
    sanitize_text
)


def get_char_count_from_payload(message):
    """
    Returns the numeric character count from a message's meta.
    """
    return message["meta"].get("char_count", 0)


def extract_payload_meta(msg):
    """
    Given a message (as a UnifiedTurn instance or dict), returns a tuple:
       (payload, merged_meta, message_id)

    Merges turn_meta and tool_meta and uses the first message's original_message_id.
    Also pulls out any invocation_reason or turns_to_purge living inside input_args
    and promotes them to the top level of merged_meta.
    """
    if isinstance(msg, UnifiedTurn):
        merged_meta = StrictDict()
        merged_meta.update(msg.turn_meta)
        merged_meta.update(msg.tool_meta)
        if "total_char_count" not in merged_meta:
            merged_meta["total_char_count"] = 0
        payload = msg.messages
    elif isinstance(msg, dict):
        merged_meta = StrictDict()
        merged_meta.update(msg["turn_meta"])
        merged_meta.update(msg["tool_meta"])
        if "total_char_count" not in merged_meta:
            merged_meta["total_char_count"] = 0
        payload = msg["messages"]
    else:
        raise TypeError("Unexpected message type: " + str(type(msg)))

    # Flatten any invocation_reason or turns_to_purge from input_args
    input_args = merged_meta.get("input_args", {})
    if isinstance(input_args, dict):
        if "invocation_reason" in input_args:
            merged_meta["invocation_reason"] = input_args["invocation_reason"]
        if "turns_to_purge" in input_args:
            merged_meta["turns_to_purge"] = input_args["turns_to_purge"]

    # original_message_id comes from the first key in payload
    keys = sorted(payload.keys())
    message_id = payload[keys[0]]["meta"].get("original_message_id")

    return payload, merged_meta, message_id


def print_turns_table():
    """
    Prints a summary table of conversation turns (excluding turn 0) using Rich.
    The dynamic column ("Filename / Input Args") is smart truncated based on available width.
    """
    console = get_console()

    # Load the current agent context (including repo_url).
    agent_role, agent_id, repo_url = get_current_agent()

    # Retrieve all messages for this (agent_role, agent_id, repo_url).
    messages = get_turns_list(agent_role, agent_id, repo_url)

    # Define columns
    columns = [
        {"header": "Del",    "justify": "left", "no_wrap": True},
        {"header": "T #",    "justify": "left", "no_wrap": True},
        {"header": "Tool",   "justify": "left", "no_wrap": True},
        {"header": "Policy","justify": "left",  "no_wrap": True},
        {"header": "KB I/O","justify": "left",  "no_wrap": True},
        {"header": "Status","justify": "left",  "no_wrap": True},
        {"header": "Args Hash","justify":"left","no_wrap": True},
        {"header": "Secs",   "justify": "left", "no_wrap": True},
        {"header": "Reason","justify":"left","no_wrap": True},
        {"header": "Purge",  "justify": "left", "no_wrap": True},
        {"header": "Filename / Input Args","justify":"left","overflow":"fold"},
    ]

    # Build title and table
    title = f"{repo_url} | {agent_role} | {agent_id} - Turns Table"
    table = create_rich_table(
        title,
        columns,
        show_lines=False,
        expand=True,
        compact=False,
        last_column_expand=True
    )

    # Group messages by turn
    turn_groups = {}
    for msg in messages:
        _, meta, _ = extract_payload_meta(msg)
        turn = meta.get("turn")
        turn_groups.setdefault(turn, []).append(msg)

    # Build rows
    rows = []
    for turn in sorted(turn_groups.keys()):
        payload, meta, _ = extract_payload_meta(turn_groups[turn][0])

        # Skip non-invocations
        if not payload.get("tool") or not meta.get("tool_name"):
            continue

        deleted_flag = "[-]" if meta.get("deleted") else "[ ]"
        turn_val     = str(meta.get("turn", "N/A"))
        tool_val     = str(meta.get("tool_name") or "n/a")
        policy_val   = str(meta.get("preservation_policy") or "n/a")
        args_hash    = str(meta.get("args_hash") or "n/a")
        rejection    = meta.get("rejection")
        status_val   = str(rejection) if rejection else str(meta.get("status") or "")

        # KB I/O
        size_in  = float(get_char_count_from_payload(payload.get("assistant", {"meta": {"char_count": 0}})))
        size_out = float(get_char_count_from_payload(payload.get("tool",      {"meta": {"char_count": 0}})))
        kb_io    = f"{size_in/1024.0:.1f}/{size_out/1024.0:.1f}"
        if kb_io.strip() == "/":
            kb_io = "0.0/0.0"

        # Execution time
        duration_str = f"{float(meta.get('execution_time', 0)):.1f}"

        # Reason & Purge (now correctly flattened)
        invocation_reason_val = str(meta.get("invocation_reason") or "")
        turns_to_purge_val    = str(meta.get("turns_to_purge")   or [])

        # Filename / Input Args
        normalized_filename = meta.get("normalized_filename", "")
        if isinstance(normalized_filename, list):
            normalized_filename = ", ".join(normalized_filename)
        primary_display = normalized_filename or str(meta.get("input_args", {}))

        rows.append([
            deleted_flag,
            turn_val,
            tool_val,
            policy_val,
            kb_io,
            status_val,
            args_hash,
            duration_str,
            invocation_reason_val,
            turns_to_purge_val,
            primary_display,
        ])

    # Compute width for the last (dynamic) column
    fixed_headers = [
        "Del","T #","Tool","Policy","KB I/O",
        "Status","Args Hash","Secs",
        "Reason","Purge"
    ]
    dynamic_col_width = compute_dynamic_column_width(
        console,
        fixed_headers,
        rows,
        fixed_count=10
    )

    # Add rows with smart truncation on the last column
    for row in rows:
        row[-1] = smart_truncate_text(sanitize_text(row[-1]), dynamic_col_width)
        table.add_row(*row)

    console.print(table)

    # Print total context size (excluding turn 0)
    total_context = sum(
        extract_payload_meta(m)[1].get("total_char_count", 0)
        for m in messages
        if extract_payload_meta(m)[1].get("turn") != 0
    ) / 1024.0
    console.print(f"Total context size: {total_context:.2f} KB", style="bold")
    console.print("")


def write_report(report_contents):
    """
    Writes a report file to the logs directory.
    Uses repository name and logs directory from configuration.
    """
    agent_role, agent_id, repo_url = get_current_agent()
    logs_dir = config.get("HOST_LOGS", ".")
    filename = f"{repo_url}_report.log"
    path     = os.path.join(logs_dir, filename)
    with open(path, "w") as f:
        f.write(report_contents)
    print(f"Report written to '{path}'")


if __name__ == "__main__":
    # For demonstration purposes, override the global turns list with sample data.
    sample_messages = [
        {
            "turn_meta": {
                "turn": 0,
                "finalized": False,
                "total_char_count": 0
            },
            "tool_meta": {
                "tool_name": "",
                "execution_time": 0,
                "pending_deletion": False,
                "deleted": False,
                "rejection": None,
                "status": "init",
                "args_hash": "hash_init",
                "preservation_policy": "N/A",
                "input_args": {"dummy": "value"}
            },
            "messages": {
                "developer": {
                    "meta": {
                        "timestamp": "2023-10-03T15:00:00Z",
                        "original_message_id": 1,
                        "char_count": 60
                    },
                    "raw": {
                        "role": "developer",
                        "content": "Initial message for turn 0."
                    }
                },
                "user": {
                    "meta": {
                        "timestamp": "2023-10-03T15:00:01Z",
                        "original_message_id": 1,
                        "char_count": 64
                    },
                    "raw": {
                        "role": "user",
                        "content": "User message for turn 0."
                    }
                }
            }
        },
        {
            "turn_meta": {
                "turn": 1,
                "finalized": True,
                "total_char_count": 1500
            },
            "tool_meta": {
                "tool_name": "example_tool",
                "execution_time": 2.5,
                "pending_deletion": False,
                "deleted": False,
                "rejection": None,
                "status": "ok",
                "args_hash": "hash123",
                "preservation_policy": "strict",
                "input_args": {
                    "arg": "value",
                    "invocation_reason": "Demo: extract code block around edit_files"
                }
            },
            "messages": {
                "assistant": {
                    "meta": {
                        "timestamp": "2023-10-03T15:05:00Z",
                        "original_message_id": 2,
                        "char_count": 800
                    },
                    "raw": {
                        "role": "assistant",
                        "content": "Assistant response."
                    }
                },
                "tool": {
                    "meta": {
                        "timestamp": "2023-10-03T15:05:02Z",
                        "original_message_id": 2,
                        "char_count": 700
                    },
                    "raw": {
                        "role": "tool",
                        "content": "Tool output."
                    }
                }
            }
        },
        {
            "turn_meta": {
                "turn": 2,
                "finalized": True,
                "total_char_count": 2000
            },
            "tool_meta": {
                "tool_name": "another_tool",
                "execution_time": 3.2,
                "pending_deletion": False,
                "deleted": True,
                "rejection": "Error occurred",
                "status": "fail",
                "args_hash": "hash456",
                "preservation_policy": "lenient",
                "input_args": {
                    "key": "value",
                    "turns_to_purge": [2, 3]
                }
            },
            "messages": {
                "assistant": {
                    "meta": {
                        "timestamp": "2023-10-03T15:10:00Z",
                        "original_message_id": 3,
                        "char_count": 1200
                    },
                    "raw": {
                        "role": "assistant",
                        "content": "Assistant response for turn 2.\nNew line test."
                    }
                },
                "tool": {
                    "meta": {
                        "timestamp": "2023-10-03T15:10:03Z",
                        "original_message_id": 3,
                        "char_count": 800
                    },
                    "raw": {
                        "role": "tool",
                        "content": "Tool output for turn 2."
                    }
                }
            }
        }
    ]

    def get_turns_list_override(*args, **kwargs):
        return sample_messages

    import modules.turns_list
    modules.turns_list.get_turns_list = get_turns_list_override

    print_turns_table()
