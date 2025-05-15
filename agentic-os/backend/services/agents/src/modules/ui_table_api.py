# modules/ui_table_api.py

"""
API Table (to be sent on the wire)

This module prints a summary table for API messages—that is, the messages that are going to be sent
on the wire to the OpenAI API. It prints the following columns:

      T # | M # | Role | Tool | Content

For each UnifiedTurn in the conversation history (skipping deleted ones), every key in
payload["messages"] is printed as a separate row.

A horizontal separator is inserted between turns. In addition, in turns that involve a tool call,
the first row (the assistant message) now shows the tool input arguments (as JSON) by checking
for normalized_args (or, if missing, input_args) in the turn’s tool_meta.

The word "json" is included in this file’s comments and payload formatting.
"""

import json
from modules.unified_turn import UnifiedTurn
from modules.turns_outbound import convert_unified_turn_to_api_message
from modules.turns_list import get_turns_list
from modules.agent_context import get_current_agent

# Import centralized Rich helpers.
from modules.ui_tables_common import (
    get_console,
    create_rich_table,
    smart_truncate_text,
    sanitize_text,
    add_rows_with_separator,
    compute_dynamic_column_width
)

def serialize_message(msg):
    """
    Serialize a UnifiedTurn message into its API payload.
    For turn 0 (i.e. system-level messages) no tool metadata is used.

    Returns a dict containing:
       • "payload"  → the API-ready payload, and
       • "turn"     → the turn number.
    """
    if not isinstance(msg, UnifiedTurn):
        raise TypeError("Unsupported message type: " + str(type(msg)))
    payload = convert_unified_turn_to_api_message(msg)
    turn = payload["turn_meta"]["turn"]
    # For turn 0, use an empty tool name.
    tool_name = "" if (turn == 0 or "tool_meta" not in payload) else payload["tool_meta"].get("tool_name", "")
    return {"payload": payload, "turn": turn}

def print_api_table():
    """
    Prints a summary API table with the columns:
         T # | M # | Role | Tool | Content

    For each UnifiedTurn from the conversation history (skipping deleted ones),
    every key in payload["messages"] is printed as a separate row.
    For the first row of a given turn, the Turn (T #) is shown; the Message ID (M #) is shown for every row.

    Normally a horizontal separator is inserted between groups.
    In turns involving tool calls, the assistant row now appends its input arguments (as JSON)
    from tool_meta (using normalized_args if available, otherwise input_args).
    """
    console = get_console()
    # Retrieve current agent context for title
    agent_role, agent_id, repo_url = get_current_agent()

    messages = get_turns_list()

    # Include repo_url | agent_role | agent_id in the title
    table_title = f"{repo_url} | {agent_role} | {agent_id} - API Table (to be sent on the wire)"
    columns_config = [
        {"header": "T #", "justify": "center"},
        {"header": "M #", "justify": "center"},
        {"header": "Role"},
        {"header": "Tool"},
        {"header": "Content"},
    ]
    table = create_rich_table(table_title, columns_config, expand=True, last_column_expand=True)

    # Flatten all rows (for dynamic width calculation) while also grouping them per turn.
    all_rows = []         # All rows for width calculation.
    grouped_rows = []     # Each element: (turn, list_of_rows)
    for msg in messages:
        if msg.tool_meta.get("deleted", False):
            continue
        ser = serialize_message(msg)
        payload = ser["payload"]
        turn_val = ser["turn"]

        rows_for_msg = []
        first_row = True             # Only the first row shows the Turn number.
        printed_tool_name = False    # For assistant messages, show tool name only once.
        for key, part in payload["messages"].items():
            role_str = part["raw"].get("role", "")
            # Get the full content (untruncated) from the message.
            content = part["raw"].get("content", "") or ""
            tool_str = ""

            if key == "assistant":
                if not printed_tool_name:
                    if "tool_calls" in part["raw"]:
                        calls = part["raw"]["tool_calls"]
                        if isinstance(calls, list) and len(calls) > 0:
                            tool_str = calls[0]["function"].get("name", "")
                            if tool_str.startswith("tool_"):
                                tool_str = tool_str[5:]
                        else:
                            tool_str = payload.get("tool_meta", {}).get("tool_name", "")
                    else:
                        tool_str = payload.get("tool_meta", {}).get("tool_name", "")
                    printed_tool_name = True

                # Append tool input arguments to the assistant message (as JSON)
                # Checking for normalized_args first, then falling back to input_args.
                tool_meta = payload.get("tool_meta", {})
                if tool_meta.get("normalized_args"):
                    args_str = json.dumps(tool_meta["normalized_args"])
                    content = content + " " + args_str if content else args_str
                elif tool_meta.get("input_args"):
                    args_str = json.dumps(tool_meta["input_args"])
                    content = content + " " + args_str if content else args_str

            elif key == "tool":
                tool_str = ""  # Do not repeat tool name for a tool message.
            else:
                tool_str = ""

            row_T = str(turn_val) if first_row else ""
            row_M = str(part.get("meta", {}).get("original_message_id", ""))
            row = [row_T, row_M, role_str, tool_str, content]
            rows_for_msg.append(row)
            all_rows.append(row)
            first_row = False

        grouped_rows.append((turn_val, rows_for_msg))

    # Sort the groups by turn number.
    grouped_rows.sort(key=lambda grp: grp[0])

    # Compute the available width for the 'Content' column based on all rows.
    fixed_headers = [col["header"] for col in columns_config[:4]]
    dynamic_content_width = compute_dynamic_column_width(console, fixed_headers, all_rows, 4)

    # Apply sanitization and dynamic truncation to each row.
    for _, group in grouped_rows:
        for row in group:
            sanitized = sanitize_text(row[4])
            row[4] = smart_truncate_text(sanitized, dynamic_content_width)

    # Add the rows to the table.
    for turn, rows in grouped_rows:
        if turn == 0:
            add_rows_with_separator(table, rows, separator_interval=len(rows) + 1)
            table.add_section()  # Force a separator after turn 0.
        else:
            add_rows_with_separator(table, rows, separator_interval=2)
            table.add_section()  # Force a separator line after non-turn0 groups.

    console.print(table)
    console.print("")  # Blank line after the table

# -----------------------------------------------------------------------------
# Demo / Testing Code (executes only when run directly)
if __name__ == "__main__":
    from modules.unified_turn import UnifiedTurn

    # Demo: Create three turns with API messages.

    # Turn 0: system-level messages (has 3 messages: system, developer, user).
    turn0 = UnifiedTurn(
        turn_meta={
            "turn": 0,
            "finalized": True,
            "total_char_count": 150
        },
        tool_meta={
            "tool_name": "",
            "execution_time": 0.0,
            "pending_deletion": False,
            "deleted": False,
            "rejection": None,
            "status": "init",
            "args_hash": "hash0",
            "preservation_policy": "N/A",
            "normalized_args": {}
        },
        messages={
            "system": {
                "meta": {
                    "timestamp": "2023-10-03T15:00:00Z",
                    "original_message_id": 0,
                    "char_count": len("System: Please respond with a valid json object. Ensure you include 'json' in your output.")
                },
                "raw": {
                    "role": "system",
                    "content": "System: Please respond with a valid json object. Ensure you include 'json' in your output."
                }
            },
            "developer": {
                "meta": {
                    "timestamp": "2023-10-03T15:00:05Z",
                    "original_message_id": 1,
                    "char_count": len("Developer: Start by using the directory_tree tool. Add random args if needed.")
                },
                "raw": {
                    "role": "developer",
                    "content": "Developer: Start by using the directory_tree tool. Add random args if needed."
                }
            },
            "user": {
                "meta": {
                    "timestamp": "2023-10-03T15:00:10Z",
                    "original_message_id": 2,
                    "char_count": len("User: Fix the bugs in this repo. START YOUR WORK NOW! This is a Java repo using JDK version 17.")
                },
                "raw": {
                    "role": "user",
                    "content": "User: Fix the bugs in this repo. START YOUR WORK NOW! This is a Java repo using JDK version 17."
                }
            }
        }
    )

    # Turn 1: API message with assistant (including a tool call) and tool reply.
    turn1 = UnifiedTurn(
        turn_meta={
            "turn": 1,
            "finalized": True,
            "total_char_count": 12300
        },
        tool_meta={
            "tool_name": "tool_write_file",
            "execution_time": 0.256,
            "pending_deletion": False,
            "deleted": False,
            "rejection": None,
            "status": "success",
            "args_hash": "hash1",
            "preservation_policy": "until-build",
            "normalized_args": {"file_path": "src/main/java/com/example/util/datetimeutils.java"}
        },
        messages={
            "assistant": {
                "meta": {
                    "timestamp": "2023-10-03T15:30:00Z",
                    "original_message_id": 101,
                    "char_count": len("Assistant response with a tool call. " * 3)
                },
                "raw": {
                    "role": "assistant",
                    "content": "Assistant response with a tool call. " * 3,
                    "tool_calls": [
                        {
                            "id": "call_exampleID",
                            "function": {
                                "name": "tool_write_file",
                                "arguments": '{ "file": "sample.txt", "mode": "w" }'
                            },
                            "timestamp": "2023-10-03T15:30:00Z"
                        }
                    ]
                }
            },
            "tool": {
                "meta": {
                    "timestamp": "2023-10-03T15:30:01Z",
                    "original_message_id": 102,
                    "char_count": len("Git reports a clean working directory.")
                },
                "raw": {
                    "role": "tool",
                    "name": "tool_write_file",
                    "content": "Git reports a clean working directory.",
                    "tool_call_id": "call_exampleID"
                }
            }
        }
    )

    # Turn 2: API message with an assistant response (no tool call) and tool reply.
    turn2 = UnifiedTurn(
        turn_meta={
            "turn": 2,
            "finalized": True,
            "total_char_count": 430
        },
        tool_meta={
            "tool_name": "none",
            "execution_time": 0.087,
            "pending_deletion": False,
            "deleted": False,
            "rejection": None,
            "status": "success",
            "args_hash": "hash2",
            "preservation_policy": "one-of",
            "normalized_args": {"dummy": "value"}
        },
        messages={
            "assistant": {
                "meta": {
                    "timestamp": "2023-10-03T15:45:00Z",
                    "original_message_id": 201,
                    "char_count": 150
                },
                "raw": {
                    "role": "assistant",
                    "content": "Assistant simple reply without tool."
                }
            },
            "tool": {
                "meta": {
                    "timestamp": "2023-10-03T15:45:01Z",
                    "original_message_id": 202,
                    "char_count": len("Tool function call response for turn 2.")
                },
                "raw": {
                    "role": "tool",
                    "name": "none",
                    "content": "Tool function call response for turn 2."
                }
            }
        }
    )

    # Override the global turns list for testing.
    messages_list = [turn0, turn1, turn2]
    def get_turns_list_override(*args, **kwargs):
        return messages_list
    import modules.turns_list as tl
    tl.get_turns_list = get_turns_list_override

    print_api_table()
