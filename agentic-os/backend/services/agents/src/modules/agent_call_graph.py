# modules/agent_call_graph.py

import threading
from typing import Tuple, List

# Thread‐safe global list of spawn edges.
# Each edge is ((parent_role, parent_id), (child_role, child_id))
_lock = threading.Lock()
_edges: List[Tuple[Tuple[str, str], Tuple[str, str]]] = []

def record_spawn(
    parent: Tuple[str, str],
    child:  Tuple[str, str]
) -> None:
    """
    Record that `parent` spawned `child`.
    parent and child are each (agent_role, agent_id).
    """
    with _lock:
        # only record each edge once
        if (parent, child) not in _edges:
            _edges.append((parent, child))

def get_graph_edges() -> List[Tuple[Tuple[str, str], Tuple[str, str]]]:
    """
    Return a snapshot of all recorded spawn edges.
    """
    with _lock:
        return list(_edges)

def format_mermaid_sequence() -> str:
    """
    Produce a Mermaid sequenceDiagram of the spawn graph.
    """
    edges = get_graph_edges()
    # collect unique participants
    participants = {p for p, c in edges} | {c for p, c in edges}
    lines: List[str] = ["sequenceDiagram"]
    # declare participants
    for role, aid in participants:
        short = aid[:8]
        alias = f"{role}_{short}"
        lines.append(f'    participant {alias} as "{role}:{short}"')
    # draw arrows
    for parent, child in edges:
        pr_alias = f"{parent[0]}_{parent[1][:8]}"
        ch_alias = f"{child[0]}_{child[1][:8]}"
        lines.append(f"    {pr_alias} ->> {ch_alias}: spawn")
    return "\n".join(lines)
