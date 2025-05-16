# modules/ui_table_agents.py

"""
Overview:
  Prints a formatted "Agents Table" using Rich, plus an ASCII-rendered
  Graphviz diagram of the global agent spawn call graph.
"""

import subprocess
from datetime import datetime

from modules.agents_running import (
    list_running_agents,
    get_current_agent_tuple,
)
from modules.turns_list import get_turns_list, get_turns_metadata
from modules.unified_turn import UnifiedTurn
from modules.ui_tables_common import get_console, create_rich_table
from modules.agent_call_graph import get_graph_edges
from shared.config import config


def relative_time(dt_obj: datetime) -> str:
    """
    Given a datetime, return a human-friendly relative time string.
    """
    now = datetime.now(dt_obj.tzinfo) if dt_obj.tzinfo else datetime.now()
    diff = now - dt_obj
    sec = diff.total_seconds()
    if sec < 60:
        n = max(1, int(sec))
        return f"{n} second{'s' if n != 1 else ''} ago"
    if sec < 3600:
        n = int(sec // 60)
        return f"{n} minute{'s' if n != 1 else ''} ago"
    if sec < 86400:
        n = int(sec // 3600)
        return f"{n} hour{'s' if n != 1 else ''} ago"
    days = diff.days
    return f"{days} day{'s' if days != 1 else ''} ago"


def print_agents_table():
    """
    Prints the Agents Table using Rich.
    """
    console = get_console()
    current = get_current_agent_tuple() or ()
    if len(current) >= 3:
        run_role, run_id, repo_url = current[:3]
    else:
        run_role = run_id = None
        repo_url = config.get("REPO_URL", "")

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

    agents = list_running_agents()

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

    for idx, agent in enumerate(sorted(agents, key=_agent_created), start=1):
        is_running = (
            agent.get("agent_role") == run_role and
            agent.get("agent_id")   == run_id
        )
        run_marker = "*" if is_running else ""
        a_role = agent.get("agent_role", "")
        a_id   = agent.get("agent_id", "")
        a_repo = agent.get("repo_url", "") or repo_url

        turns = get_turns_list(a_role, a_id, a_repo)
        total_turns = len(turns)
        metadata_str = str(get_turns_metadata(a_role, a_id, a_repo) or {})

        # find the most recent timestamp in the turn history
        dt_last = None
        for ut in reversed(turns):
            msgs = ut.messages if isinstance(ut, UnifiedTurn) else ut.get("messages", {})
            for role_key in ("tool", "assistant", "user", "system"):
                m = msgs.get(role_key, {})
                ts = m.get("meta", {}).get("timestamp") or m.get("raw", {}).get("timestamp")
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
    console.print(f"Total agents: {len(agents)}")
    if run_role and run_id:
        console.print(f"Currently running agent: {run_role}_{run_id}")
    else:
        console.print("No running agent found.")


def print_call_graph_table():
    """
    Prints the global agent spawn call graph rendered as ASCII via Graphviz.
    """
    console = get_console()
    edges = get_graph_edges()

    # Build DOT source
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        "  labelloc=\"t\";",
        "  label=\"Agent Spawn Graph\";",
    ]
    for (pr, pi), (cr, ci) in edges:
        src = f"\"{pr}_{pi[:8]}\""
        dst = f"\"{cr}_{ci[:8]}\""
        lines.append(f"  {src} -> {dst};")
    lines.append("}")
    dot_src = "\n".join(lines)

    console.print("\n[bold]Agent Spawn Graph (ASCII via Graphviz)[/bold]\n")
    try:
        proc = subprocess.Popen(
            ["dot", "-Tascii"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        out, _ = proc.communicate(dot_src, timeout=5.0)
        console.print(out)
    except FileNotFoundError:
        console.print("[red]Graphviz 'dot' not found. Install Graphviz or see DOT source below:[/red]")
        console.print(dot_src)
    except Exception as e:
        console.print(f"[red]Error running Graphviz: {e}[/red]")
        console.print(dot_src)


if __name__ == "__main__":
    print_agents_table()
    print_call_graph_table()
