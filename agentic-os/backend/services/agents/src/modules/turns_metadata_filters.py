# modules/turns_metadata_filters.py

from typing import Any, Callable, Dict, List
from modules.unified_turn import UnifiedTurn
from shared.logger import logger

ToolFilterFunc = Callable[[UnifiedTurn, Dict[str, Any]], None]
_registry: Dict[str, List[ToolFilterFunc]] = {}


def register_tool_filter(tool_name: str):
    """
    Decorator to register a function that will be called whenever
    a turn with turn_meta['tool_name']==tool_name is added.
    """
    def decorator(fn: ToolFilterFunc) -> ToolFilterFunc:
        _registry.setdefault(tool_name, []).append(fn)
        return fn
    return decorator


def apply_tool_filters(turn: UnifiedTurn, metadata: Dict[str, Any]) -> None:
    """
    Run all registered filters for this turn's tool_name,
    passing them the turn and the conversation metadata dict.
    """
    tool = turn.turn_meta.get("tool_name")
    if not tool:
        return
    for fn in _registry.get(tool, []):
        try:
            fn(turn, metadata)
        except Exception as e:
            logger.warning(
                f"turns_metadata_filters: error in filter {fn.__name__} "
                f"for tool {tool}: {e}"
            )


#
# Example filter for tool_fetch_github_issues:
#
@register_tool_filter("tool_fetch_github_issues")
def _github_issues_filter(turn: UnifiedTurn, metadata: Dict[str, Any]) -> None:
    args = turn.turn_meta.get("input_args", {}) or {}
    title = args.get("title")
    users = args.get("users") or args.get("assignees")
    if title:
        metadata["issue_title"] = title
    if users:
        metadata["issue_assignees"] = users
