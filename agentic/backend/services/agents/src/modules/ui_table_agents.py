# modules/ui_table_agents.py

"""
Overview:
  This module prints a formatted "Agents Table" using a Rich-based table infrastructure,
  and also prints the current agent call-stack in its own table.
"""

from datetime import datetime
from modules.agents_running import list_running_agents, get_current_agent_tuple
from modules.turns_list import get_turns_list
from modules.unified_turn import UnifiedTurn
from modules.ui_tables_common import get_console, create_rich_table
from shared.config import config
from shared.client_agents import get_agent_stack     # ← new import

def relative_time(dt_obj):
    """
    Given a datetime object, returns a human-friendly relative time string,
    e.g. "3 hours ago", "5 seconds ago", or "1 second ago".
    """
    now = datetime.now(dt_obj.tzinfo) if dt_obj.tzinfo else datetime.now()
    diff = now - dt_obj
    total_sec = diff.total_seconds()
    if total_sec < 60:
        sec = max(1, int(total_sec))
        return f"{sec} second{'s' if sec != 1 else ''} ago"
    if total_sec < 3600:
        mins = int(total_sec // 60)
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if total_sec < 86400:
        hrs = int(total_sec // 3600)
        return f"{hrs} hour{'s' if hrs != 1 else ''} ago"
    days = diff.days
    return f"{days} day{'s' if days != 1 else ''} ago"

def print_agents_table():
    """
    Prints the Agents Table using Rich.
    """
    console = get_console()
    
    # Define columns
    columns = [
        {"header": "#",          "justify": "center", "style": "dim"},
        {"header": "Running",    "justify": "center", "style": "dim"},
        {"header": "Agent Role", "justify": "left"},
        {"header": "Agent ID",   "justify": "left"},
        {"header": "Total Turns","justify": "center"},
        {"header": "Last Turn",  "justify": "center"},
    ]
    table = create_rich_table("Agents Table", columns, compact=False)
    table.expand = False
    for col in table.columns:
        col.padding = (0, 1)
    
    agents = list_running_agents()
    def _get_created(agent):
        ts = agent.get("created_at") or agent.get("timestamp")
        if isinstance(ts, (int, float)):
            try: return datetime.fromtimestamp(ts)
            except: return datetime.min
        if isinstance(ts, str):
            try: return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except: return datetime.min
        return datetime.min
    sorted_agents = sorted(agents, key=_get_created)
    
    full_running = get_current_agent_tuple() or ()
    run_role     = full_running[0] if len(full_running) > 0 else None
    run_id       = full_running[1] if len(full_running) > 1 else None
    
    for idx, agent in enumerate(sorted_agents, start=1):
        is_running  = (agent.get("agent_role") == run_role and agent.get("agent_id") == run_id)
        run_marker  = "*" if is_running else ""
        
        repo_url   = agent.get("repo_url") or config.get("REPO_URL", "")
        turns       = get_turns_list(agent.get("agent_role", ""), agent.get("agent_id", ""), repo_url)
        
        total_turns = len(turns)
        last_turn_str = "N/A"
        dt_last      = None
        
        if total_turns > 0:
            # find most recent timestamp in this turn list
            for turn in reversed(turns):
                ts_direct = None
                messages  = {}
                if isinstance(turn, UnifiedTurn):
                    messages = turn.messages
                elif isinstance(turn, dict):
                    messages  = turn.get("messages", {})
                    ts_direct = turn.get("timestamp")
                # legacy timestamp
                if ts_direct:
                    try:
                        dt_last = (datetime.fromtimestamp(ts_direct)
                                   if isinstance(ts_direct, (int, float))
                                   else datetime.fromisoformat(ts_direct.replace("Z", "+00:00")))
                    except:
                        dt_last = None
                    if dt_last: break
                # tool
                ts_tool = messages.get("tool", {}).get("meta", {}).get("timestamp")
                if ts_tool:
                    try:
                        dt_last = (datetime.fromtimestamp(ts_tool)
                                   if isinstance(ts_tool, (int, float))
                                   else datetime.fromisoformat(ts_tool.replace("Z", "+00:00")))
                    except:
                        dt_last = None
                    if dt_last: break
                # assistant
                ts_assist = messages.get("assistant", {}).get("meta", {}).get("timestamp")
                if ts_assist:
                    try:
                        dt_last = (datetime.fromtimestamp(ts_assist)
                                   if isinstance(ts_assist, (int, float))
                                   else datetime.fromisoformat(ts_assist.replace("Z", "+00:00")))
                    except:
                        dt_last = None
                    if dt_last: break
        
        # fallback to agent metadata
        if not dt_last:
            ts_agent = agent.get("timestamp") or agent.get("created_at")
            if ts_agent:
                try:
                    dt_last = (datetime.fromtimestamp(ts_agent)
                               if isinstance(ts_agent, (int, float))
                               else datetime.fromisoformat(ts_agent.replace("Z", "+00:00")))
                except:
                    dt_last = None
        
        if dt_last:
            last_turn_str = relative_time(dt_last)
        
        table.add_row(
            str(idx),
            run_marker,
            agent.get("agent_role", ""),
            agent.get("agent_id", ""),
            str(total_turns),
            last_turn_str,
        )
        
    console.print(table)
    console.print(f"Total agents: {len(sorted_agents)}")
    if run_role and run_id:
        console.print(f"Currently running agent: {run_role}_{run_id}")
    else:
        console.print("No running agent found.")

def print_call_stack_table():
    """
    Prints the current agent call-stack using Rich.
    """
    console = get_console()
    stack = get_agent_stack()  # client API call
    if not stack:
        console.print("[dim]Call stack is empty.[/dim]")
        return

    columns = [
        {"header": "Level",      "justify": "center", "style": "dim"},
        {"header": "Agent Role", "justify": "left"},
        {"header": "Agent ID",   "justify": "left"},
        {"header": "Repo URL",   "justify": "left"},
    ]
    table = create_rich_table("Agent Call Stack (top first)", columns, compact=False)
    table.expand = False
    for col in table.columns:
        col.padding = (0,1)

    # show top of stack first
    for level, entry in enumerate(reversed(stack), start=1):
        table.add_row(
            str(level),
            entry.get("agent_role", ""),
            entry.get("agent_id", ""),
            entry.get("repo_url", ""),
        )

    console.print(table)
    console.print(f"Stack depth: {len(stack)}")

if __name__ == "__main__":
    print_agents_table()
    print()  # blank line
    print_call_stack_table()
