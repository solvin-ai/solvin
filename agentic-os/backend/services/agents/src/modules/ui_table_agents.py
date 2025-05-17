# modules/ui_table_agents.py

"""
Overview:
  Prints a formatted "Agents Table" using Rich, plus a simple ASCII-rendered
  call graph of the global agent spawn.
"""

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

    # helper to keep a string ≤ max_len by ellipsizing in the middle
    def smart_truncate(s: str, max_len: int = 80) -> str:
        if len(s) <= max_len:
            return s
        head = max_len // 2
        tail = max_len - head - 1
        return s[:head] + "…" + s[-tail:]

    columns = [
        {"header": "State",        "justify": "center"},
        {"header": "#",            "justify": "center", "style": "dim"},
        {"header": "Running",      "justify": "center", "style": "dim"},
        {"header": "Repo URL",     "justify": "left"},
        {"header": "Agent Role",   "justify": "left"},
        {"header": "Agent ID",     "justify": "left"},
        {"header": "Total Turns",  "justify": "center"},
        {"header": "Last Turn",    "justify": "center"},
        {"header": "Reason",       "justify": "left"},
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
        a_role = agent.get("agent_role", "")
        a_id   = agent.get("agent_id", "")
        a_repo = agent.get("repo_url", "") or repo_url

        is_running = (a_role == run_role and a_id == run_id)
        run_marker = "*" if is_running else ""

        turns = get_turns_list(a_role, a_id, a_repo)
        total_turns = len(turns)

        meta = get_turns_metadata(a_role, a_id, a_repo) or {}
        state = meta.get("state", "idle")
        # drop 'state' from the metadata display
        other_meta = {k: v for k, v in meta.items() if k != "state"}
        metadata_str = str(other_meta)
        reason_str = smart_truncate(metadata_str, 80)

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
            state,
            str(idx),
            run_marker,
            a_repo,
            a_role,
            a_id,
            str(total_turns),
            last_turn_str,
            reason_str,
        )

    console.print(table)
    console.print(f"Total agents: {len(agents)}")
    if run_role and run_id:
        console.print(f"Currently running agent: {run_role}_{run_id}")
    else:
        console.print("No running agent found.")


def print_call_graph_table():
    """
    Prints the global agent spawn call graph as a simple ASCII tree.
    """
    console = get_console()
    edges = get_graph_edges()

    # Build adjacency list and collect nodes
    adjacency = {}
    all_nodes = set()
    child_nodes = set()
    for (pr, pi), (cr, ci) in edges:
        parent = f"{pr}_{pi[:8]}"
        child  = f"{cr}_{ci[:8]}"
        adjacency.setdefault(parent, []).append(child)
        all_nodes.add(parent)
        all_nodes.add(child)
        child_nodes.add(child)

    # Sort adjacency lists for stable output
    for lst in adjacency.values():
        lst.sort()

    # Roots are those parents that never appear as a child
    roots = sorted(n for n in all_nodes if n not in child_nodes)

    console.print("\n[bold]Agent Spawn Graph (ASCII)[/bold]\n")

    if not all_nodes:
        console.print("  (no spawn graph data)")
        return

    def _render(node: str, prefix: str = "", is_last: bool = True):
        """Recursively prints node and its children with tree branches."""
        branch = "└── " if is_last else "├── "
        console.print(f"{prefix}{branch}{node}")
        children = adjacency.get(node, [])
        for i, child in enumerate(children):
            last_child = (i == len(children) - 1)
            new_prefix = prefix + ("    " if is_last else "│   ")
            _render(child, new_prefix, last_child)

    # If there are no clear roots (i.e. a cycle or every node is a child),
    # just treat every node as a root to ensure we print something.
    if not roots:
        roots = sorted(all_nodes)

    # Print each tree
    for root in roots:
        console.print(root)
        children = adjacency.get(root, [])
        for j, child in enumerate(children):
            _render(child, prefix="", is_last=(j == len(children) - 1))


if __name__ == "__main__":
    print_agents_table()
    print_call_graph_table()
