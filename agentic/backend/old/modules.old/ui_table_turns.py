# modules/ui_table_turns.py

"""
Overview:
  • This module prints a summary turns table for conversation history (excluding turn 0).
  • It retrieves conversation history from modules.turns_list.
  • The table displays the following columns:
         Del | T # | Tool | Policy | KB I/O | Status | Args Hash | Secs | Filename / Input Args
  • For each turn the first message is used to aggregate metadata.
  • The dynamic column ("Filename / Input Args") is smart truncated based on the available space,
    which is calculated using centralized helpers in ui_tables_common.
  
Usage:
  • Calling print_turns_table() prints the table to the terminal.
"""

__all__ = ["print_turns_table", "write_report"]

import os
from pprint import pformat

from modules.unified_turn import UnifiedTurn, StrictDict
from modules.turns_list import get_turns_list
from modules.config import config

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
    """
    if isinstance(msg, UnifiedTurn):
        merged_meta = StrictDict()
        merged_meta.update(msg.turn_meta)
        merged_meta.update(msg.tool_meta)
        if "total_char_count" not in merged_meta:
            merged_meta["total_char_count"] = 0
        payload = msg.messages
        keys = sorted(payload.keys())
        message_id = payload[keys[0]]["meta"].get("original_message_id")
        return payload, merged_meta, message_id
    elif isinstance(msg, dict):
        merged_meta = StrictDict()
        merged_meta.update(msg["turn_meta"])
        merged_meta.update(msg["tool_meta"])
        if "total_char_count" not in merged_meta:
            merged_meta["total_char_count"] = 0
        payload = msg["messages"]
        keys = sorted(payload.keys())
        message_id = payload[keys[0]]["meta"].get("original_message_id")
        return payload, merged_meta, message_id
    else:
        raise TypeError("Unexpected message type: " + str(type(msg)))

def print_turns_table():
    """
    Prints a summary table of conversation turns (excluding turn 0) using Rich.
    The dynamic column ("Filename / Input Args") is smart truncated based on available width.
    """
    console = get_console()
    messages = get_turns_list()
    repo_name = config.get("REPO_NAME", scope="service.repos", "default_repo")

    # All columns are now set to left alignment.
    columns = [
        {"header": "Del",    "justify": "left", "no_wrap": True},
        {"header": "T #",    "justify": "left", "no_wrap": True},
        {"header": "Tool",   "justify": "left", "no_wrap": True},
        {"header": "Policy", "justify": "left", "no_wrap": True},
        {"header": "KB I/O", "justify": "left", "no_wrap": True},
        {"header": "Status", "justify": "left", "no_wrap": True},
        {"header": "Args Hash", "justify": "left", "no_wrap": True},
        {"header": "Secs",   "justify": "left", "no_wrap": True},
        {"header": "Filename / Input Args", "justify": "left", "overflow": "fold"}
    ]

    # Create a Rich Table using our common helper.
    table = create_rich_table("Turns Table",
                              columns,
                              show_lines=False,
                              expand=True,
                              compact=False,
                              last_column_expand=True)

    # Group messages by turn.
    turn_groups = {}
    for msg in messages:
        _, meta, _ = extract_payload_meta(msg)
        turn = meta.get("turn")
        turn_groups.setdefault(turn, []).append(msg)

    # Gather rows for turns (skipping turn 0).
    rows = []
    for turn in sorted(turn_groups.keys()):
        if turn == 0:
            continue
        msgs = turn_groups[turn]
        msg = msgs[0]  # Use the first message to aggregate metadata.
        payload, meta, _ = extract_payload_meta(msg)

        deleted_flag = "[-]" if meta.get("deleted") else "[ ]"
        turn_val   = str(meta.get("turn", "N/A"))
        tool_val   = str(meta.get("tool_name") or "n/a")
        policy_val = str(meta.get("preservation_policy") or "n/a")
        args_hash  = str(meta.get("args_hash") or "n/a")
        rejection = meta.get("rejection")
        if rejection:
           status_val = str(rejection)
        else:
           status_val = str(meta.get("status") or "")

        # Compute KB I/O from character counts.
        assistant_payload = payload.get("assistant", {"meta": {"char_count": 0}})
        tool_payload      = payload.get("tool", {"meta": {"char_count": 0}})
        size_in  = float(get_char_count_from_payload(assistant_payload))
        size_out = float(get_char_count_from_payload(tool_payload))
        kb_io    = f"{size_in/1024.0:.1f}/{size_out/1024.0:.1f}"
        if kb_io.strip() == "/":
            kb_io = "0.0/0.0"

        exec_time    = float(meta.get("execution_time", 0))
        duration_str = f"{exec_time:.1f}"

        # For the last column: prefer normalized_filename over input_args.
        input_args = meta.get("input_args", {})
        normalized_filename = meta.get("normalized_filename", "")
        if isinstance(normalized_filename, list):
            normalized_filename = ", ".join(normalized_filename)
        primary_display = normalized_filename if normalized_filename != "" else str(input_args)

        row = [deleted_flag, turn_val, tool_val, policy_val, kb_io, status_val, args_hash, duration_str, primary_display]
        rows.append(row)

    # Compute available width for the dynamic column (last column; fixed columns are the first eight).
    fixed_headers = ["Del", "T #", "Tool", "Policy", "KB I/O", "Status", "Args Hash", "Secs"]
    dynamic_col_width = compute_dynamic_column_width(console, fixed_headers, rows, fixed_count=8)

    # Smart truncate the dynamic column after sanitizing it.
    for row in rows:
        row[8] = smart_truncate_text(sanitize_text(row[8]), dynamic_col_width)
        table.add_row(*row)

    console.print(table)

    # Compute and print the total context size (excluding turn 0).
    total_context = sum(
        extract_payload_meta(msg)[1].get("total_char_count", 0)
        for msg in messages if extract_payload_meta(msg)[1].get("turn") != 0
    ) / 1024.0
    console.print(f"Total context size: {total_context:.2f} KB", style="bold")
    console.print("")

def write_report(report_contents):
    """
    Writes a report file to the logs directory.
    Uses repository name and logs directory from configuration.
    """
    repo_name = config.get("REPO_NAME", scope="service.repos", "default_repo")
    logs_dir  = config.get("HOST_LOGS", ".")
    filename  = f"{repo_name}_report.log"
    path      = os.path.join(logs_dir, filename)
    with open(path, "w") as f:
        f.write(report_contents)
    print("Report written to '{}'".format(path))

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
        # Sample message for turn 1.
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
                "input_args": {"arg": "value"}
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
        # Sample message for turn 2.
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
                "input_args": {"key": "value"}
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

    # Set repository name for testing.
    config.set("REPO_NAME")
    print_turns_table()
