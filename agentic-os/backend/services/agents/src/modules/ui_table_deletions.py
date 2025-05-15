# modules/ui_table_deletions.py

"""
This module iterates over UnifiedTurn objects (fetched from the global turns list)
and prints a table showing details for all deleted turns. Deletions are now considered
per turn (grouping all UnifiedTurn objects with the same turn number).

For each deleted turn, the following details are printed (from turn_meta and tool_meta):
  • T #             – The conversation turn number (turn_meta["turn"])
  • Tool            – The associated tool (tool_meta["tool_name"], with any leading "tool_" removed)
  • Status          – The status field (tool_meta["status"])
  • Policy          – The preservation policy (tool_meta["preservation_policy"])
  • Deletion Reason – The deletion reason (tool_meta["rejection"])

This module now uses the shared Rich-based table helpers defined in ui_tables_common.py.
"""

from modules.ui_tables_common import get_console, create_rich_table, add_rows_with_separator
from modules.turns_list import get_turns_list
from modules.agent_context import get_current_agent


def print_deletions_table():
    """
    Fetches the global conversation history and prints a deletion-history table
    that includes only deleted turns. The table groups entries by turn number.
    
    (Uses add_rows_with_separator with separator_interval=0 to ensure no horizontal line separators.)
    """
    console = get_console()
    
    # pull context
    agent_role, agent_id, repo_url = get_current_agent()
    
    # include context in title
    title = f"{repo_url} | {agent_role} | {agent_id} - Deletion Table"
    
    # Define the columns with headers and optional styling.
    # (No min_width is provided so that no column is forced to a minimal width.)
    columns = [
        {"header": "T #", "justify": "center", "style": "dim"},
        {"header": "Tool"},
        {"header": "Status", "justify": "center"},
        {"header": "Policy", "justify": "center"},
        {"header": "Deletion Reason"},  # This column will expand to fill available space.
    ]
    
    # Create the Rich table using our common helper.
    table = create_rich_table(title, columns)
    
    # Fetch the global turns. Each turn is an instance of UnifiedTurn.
    turns = get_turns_list() or []
    
    # Group turns by their turn number (only include deleted ones).
    turn_groups = {}
    for turn_obj in turns:
        if not turn_obj.tool_meta.get("deleted", False):
            continue
        turn_val = str(turn_obj.turn_meta.get("turn", "N/A"))
        turn_groups.setdefault(turn_val, []).append(turn_obj)
    
    # Sort the groups numerically (if possible).
    sorted_turns = sorted(
        turn_groups.keys(),
        key=lambda t: int(t) if t.isdigit() else float('inf')
    )
    
    # Accumulate table rows.
    rows = []
    for turn in sorted_turns:
        group = turn_groups[turn]
        rep_turn = group[0]
        
        # Process the tool name: remove any leading "tool_" if present.
        tool_name = rep_turn.tool_meta.get("tool_name", "").strip()
        if tool_name.lower().startswith("tool_"):
            tool_name = tool_name[5:]
        
        status       = str(rep_turn.tool_meta.get("status", ""))
        policy       = str(rep_turn.tool_meta.get("preservation_policy", ""))
        deletion_rev = str(rep_turn.tool_meta.get("rejection", ""))
        
        # Build the row as a list.
        rows.append([
            str(turn),
            tool_name,
            status,
            policy,
            deletion_rev,
        ])
    
    # Add rows to the table with no horizontal separator between rows.
    add_rows_with_separator(table, rows, separator_interval=0)
    
    console.print(table)


# -----------------------------------------------------------------------------
# Testing / Demonstration Code (executes only when run directly)
if __name__ == "__main__":
    # Dummy UnifiedTurn-like class for demonstration purposes.
    class DummyTurn:
        def __init__(self, turn, tool_name, deleted, status, policy, rejection):
            self._turn_meta = {"turn": turn, "total_char_count": 0}
            self._tool_meta = {"tool_name": tool_name, "deleted": deleted,
                               "status": status, "preservation_policy": policy, "rejection": rejection}
            self._messages = {}  # Not used for this table

        @property
        def turn_meta(self):
            return self._turn_meta

        @property
        def tool_meta(self):
            return self._tool_meta

        @property
        def messages(self):
            return self._messages

    # Create some dummy turns for testing.
    dummy_turns = [
        DummyTurn(1, "tool_git_status", True, "failed", "one-time", "Reason A"),
        DummyTurn(1, "tool_git_status", True, "failed", "one-time", "Reason A"),
        DummyTurn(2, "", True, "success", "persistent", "Reason B"),
        DummyTurn(8, "tool_analyzer", True, "failure", "build", "Reason C")
    ]

    # For testing, override get_turns_list to return the dummy turns.
    def get_turns_list_override(*args, **kwargs):
        return dummy_turns

    import modules.turns_list as tl
    tl.get_turns_list = get_turns_list_override

    print_deletions_table()
