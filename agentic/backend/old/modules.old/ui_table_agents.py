# modules/ui_table_agents.py

"""
Overview:
  This module prints a formatted "Agents Table" using a Rich-based table infrastructure.
  It displays all live agents, marks the currently running agent with an asterisk in the RUN column,
  and for each agent displays:
    • AGENT TYPE,
    • AGENT ID,
    • TOTAL TURNS (from the turns list),
    • LAST TURN (as a relative time, e.g. "5 minutes ago").

  Timestamps are determined by checking for a legacy "timestamp", then the tool role,
  and lastly the assistant role.

Note: System initialization via agent_manager.init_agent_manager() is assumed.
"""

from datetime import datetime
from modules.agent_manager import list_live_agents, get_running_agent
from modules.turns_list import get_turns_list
from modules.unified_turn import UnifiedTurn
from modules.ui_tables_common import get_console, create_rich_table

def relative_time(dt_obj):
    """
    Given a datetime object, returns a human-friendly relative time string,
    e.g. "3 hours ago".
    """
    now = datetime.now(dt_obj.tzinfo) if dt_obj.tzinfo else datetime.now()
    diff = now - dt_obj
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds >= 3600:
        hrs = diff.seconds // 3600
        return f"{hrs} hour{'s' if hrs != 1 else ''} ago"
    elif diff.seconds >= 60:
        mins = diff.seconds // 60
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    else:
        return f"{diff.seconds} second{'s' if diff.seconds != 1 else ''} ago"

def print_agents_table():
    """
    Prints the Agents Table using Rich.
    """
    console = get_console()
    
    # Define the table columns with header text.
    columns = [
        {"header": "Run", "justify": "center", "style": "dim"},
        {"header": "Agent Type", "justify": "left"},
        {"header": "Agent ID", "justify": "left"},
        {"header": "Total Turns", "justify": "center"},
        {"header": "Last Turn", "justify": "center"},
    ]
    
    # Create a standardized Rich table.
    # Use compact=False so that our manual padding is preserved,
    # and set table.expand = False so it doesn’t fill the entire console width.
    table = create_rich_table("Agents Table", columns, compact=False)
    table.expand = False  # Prevent table from stretching to match full console width
    
    # Set each column’s padding to have one space on the left and right.
    for col in table.columns:
        col.padding = (0, 1)
    
    # Retrieve agents and sort them.
    agents = list_live_agents()
    sorted_agents = sorted(agents, key=lambda a: (a.get("agent_role", ""), a.get("agent_id", "")))
    running_agent = get_running_agent()  # Expected to be a tuple like (agent_role, agent_id)
    
    # Process each agent.
    for agent in sorted_agents:
        # Mark the running agent with an asterisk.
        mark = "*" if running_agent and (agent.get("agent_role"), agent.get("agent_id")) == running_agent else ""
        
        # Retrieve the agent's conversation turns.
        turns = get_turns_list(agent.get("agent_role", ""), agent.get("agent_id", ""))
        total_turns = len(turns)
        last_turn_str = "N/A"
        dt_last = None
        
        if total_turns > 0:
            # Look for the most recent timestamp by iterating in reverse.
            for turn in reversed(turns):
                messages = {}
                ts_direct = None

                if isinstance(turn, UnifiedTurn):
                    messages = turn.messages
                elif isinstance(turn, dict):
                    messages = turn.get("messages", {})
                    ts_direct = turn.get("timestamp")
                else:
                    continue

                # 1. Use the legacy timestamp if available.
                if ts_direct:
                    try:
                        if isinstance(ts_direct, (int, float)):
                            dt_last = datetime.fromtimestamp(ts_direct)
                        else:
                            dt_last = datetime.fromisoformat(ts_direct.replace("Z", "+00:00"))
                    except Exception:
                        dt_last = None
                    if dt_last:
                        break

                # 2. Use the tool role timestamp.
                ts_tool = messages.get("tool", {}).get("meta", {}).get("timestamp")
                if ts_tool:
                    try:
                        if isinstance(ts_tool, (int, float)):
                            dt_last = datetime.fromtimestamp(ts_tool)
                        else:
                            dt_last = datetime.fromisoformat(ts_tool.replace("Z", "+00:00"))
                    except Exception:
                        dt_last = None
                    if dt_last:
                        break

                # 3. Fallback to the assistant role timestamp.
                ts_assistant = messages.get("assistant", {}).get("meta", {}).get("timestamp")
                if ts_assistant:
                    try:
                        if isinstance(ts_assistant, (int, float)):
                            dt_last = datetime.fromtimestamp(ts_assistant)
                        else:
                            dt_last = datetime.fromisoformat(ts_assistant.replace("Z", "+00:00"))
                    except Exception:
                        dt_last = None
                    if dt_last:
                        break

        if dt_last:
            last_turn_str = relative_time(dt_last)
        
        # Add the row to the table.
        table.add_row(
            mark,
            str(agent.get("agent_role", "")),
            str(agent.get("agent_id", "")),
            str(total_turns),
            last_turn_str,
        )
        
    # Render the table.
    console.print(table)
    
    # Print a summary.
    console.print(f"Total agents: {len(sorted_agents)}")
    if running_agent:
        console.print(f"Currently running agent: {running_agent[0]}_{running_agent[1]}")
    else:
        console.print("No running agent found.")

if __name__ == "__main__":
    print_agents_table()
