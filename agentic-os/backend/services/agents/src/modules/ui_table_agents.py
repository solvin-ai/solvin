# modules/ui_table_agents.py

"""
Overview:
  This module prints a formatted "Agents Table" using Rich-based table infrastructure,
  and also prints the current agent call-stack in its own table.
  Now supports per-task scoping: all agent and turn lookups include repo_url.
"""

from datetime import datetime
from modules.agents_running import (
    list_running_agents,
    get_current_agent_tuple,
    get_agent_stack
)
from modules.turns_list import get_turns_list, get_turns_metadata
from modules.unified_turn import UnifiedTurn
from modules.ui_tables_common import get_console, create_rich_table
from shared.config import config


def relative_time(dt_obj: datetime) -> str:
    """
    Given a datetime object, returns a human-friendly relative time string,
    e.g. "3 hours ago", "5 seconds ago", or "1 day ago".
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

    # determine current context (repo_url), falling back to config
    current = get_current_agent_tuple() or ()
    if len(current) >= 3:
        # core now returns at least (role, id, repo_url)
        run_role, run_id, repo_url = current[:3]
    else:
        run_role = run_id = None
        repo_url = config.get("REPO_URL", "")

    # table columns
    columns = [
        {"header": "#",           "justify": "center", "style": "dim"},
        {"header": "Running",     "justify": "center", "style": "dim"},
        {"header": "Repo URL",    "justify": "left"},
        {"header": "Agent Role",  "justify": "left"},
        {"header": "Agent ID",    "justify": "left"},
        {"header": "Total Turns", "justify": "center"},
        {"header": "Last Turn",   "justify": "center"},
        {"header": "Metadata",    "justify": "left"},
    ]
    table = create_rich_table("Agents Table", columns, compact=False)
    table.expand = False
    for col in table.columns:
        col.padding = (0, 1)

    # fetch all agents (no arg → uses current-agent's repo_url under the hood)
    agents = list_running_agents()

    # sort by creation timestamp
    def _agent_created(a: dict) -> datetime:
        ts = a.get("created_at") or a.get("timestamp")
        if isinstance(ts, (int, float)):
            try:
                return datetime.fromtimestamp(ts)
            except:
                pass
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except:
                pass
        return datetime.min

    sorted_agents = sorted(agents, key=_agent_created)

    # build rows
    for idx, agent in enumerate(sorted_agents, start=1):
        is_running = (
            agent.get("agent_role") == run_role
            and agent.get("agent_id")   == run_id
        )
        run_marker = "*" if is_running else ""

        a_role = agent.get("agent_role", "")
        a_id   = agent.get("agent_id", "")
        a_repo = agent.get("repo_url", "") or repo_url

        # fetch turn history for each agent
        turns = get_turns_list(a_role, a_id, a_repo)
        total_turns = len(turns)

        # fetch conversation-level metadata
        metadata = get_turns_metadata(a_role, a_id, a_repo) or {}
        metadata_str = str(metadata)

        # find most recent timestamp among messages
        dt_last = None
        for ut in reversed(turns):
            msgs = ut.messages if isinstance(ut, UnifiedTurn) else ut.get("messages", {})
            for role_key in ("tool", "assistant", "user", "system"):
                m = msgs.get(role_key, {})
                ts = (
                    m.get("meta", {}).get("timestamp")
                    or m.get("raw", {}).get("timestamp")
                )
                if ts:
                    try:
                        dt = (
                            datetime.fromtimestamp(ts)
                            if isinstance(ts, (int, float))
                            else datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        )
                    except:
                        dt = None
                    if dt:
                        dt_last = dt
                        break
            if dt_last:
                break

        # fallback to agent metadata timestamp
        if not dt_last:
            ts_agent = agent.get("created_at") or agent.get("timestamp")
            if ts_agent:
                try:
                    dt_last = (
                        datetime.fromtimestamp(ts_agent)
                        if isinstance(ts_agent, (int, float))
                        else datetime.fromisoformat(ts_agent.replace("Z", "+00:00"))
                    )
                except:
                    dt_last = None

        last_turn_str = relative_time(dt_last) if dt_last else "N/A"

        table.add_row(
            str(idx),
            run_marker,
            a_repo,
            a_role,
            a_id,
            str(total_turns),
            last_turn_str,
            metadata_str,
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
    stack = get_agent_stack()  # returns list of dicts with repo_url, agent_role, agent_id

    if not stack:
        console.print("[dim]Call stack is empty.[/dim]")
        return

    columns = [
        {"header": "Level",      "justify": "center", "style": "dim"},
        {"header": "Repo URL",   "justify": "left"},
        {"header": "Agent Role", "justify": "left"},
        {"header": "Agent ID",   "justify": "left"},
    ]
    table = create_rich_table("Agent Call Stack (top first)", columns, compact=False)
    table.expand = False
    for col in table.columns:
        col.padding = (0, 1)

    # top of stack first
    for level, entry in enumerate(reversed(stack), start=1):
        table.add_row(
            str(level),
            entry.get("repo_url", ""),
            entry.get("agent_role", ""),
            entry.get("agent_id", ""),
        )

    console.print(table)
    console.print(f"Stack depth: {len(stack)}")


if __name__ == "__main__":
    print_agents_table()
    print()  # blank line
    print_call_stack_table()
