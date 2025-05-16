# modules/turns_list.py

import time
from typing import Any, Dict, List, Optional, Tuple

from modules.db_turns    import (
    load_turns                as _load_turns,
    save_turns                as _save_turns,
    delete_turns              as _delete_turns,
    query_turns               as _query_turns,
    load_conversation_metadata,
    save_conversation_metadata,
)
from modules.db_state    import load_state, save_state
from modules.prompts     import initialize_initial_turn_history
from modules.unified_turn import UnifiedTurn
from shared.logger        import logger

# new import for tool → metadata filters
from modules.turns_metadata_filters import apply_tool_filters

MAX_TURNS_LISTS_IN_MEMORY = 10


class TurnHistory:
    # class‐level cache + LRU tracker
    _instances: Dict[Tuple[str, str, str], "TurnHistory"] = {}
    _lru:       Dict[Tuple[str, str, str], float]         = {}

    def __init__(self,
                 agent_role: str,
                 agent_id:   str,
                 repo_url:   str):
        self.agent_role = agent_role
        self.agent_id   = agent_id
        self.repo_url   = repo_url
        self._key       = (agent_role, agent_id, repo_url)

        # 1) load persisted turns
        self.turns: List[UnifiedTurn] = _load_turns(
            repo_url, agent_role, agent_id
        ) or []

        # 2) if no history at all, seed turn-0 (else do nothing)
        if not self.turns:
            initialize_initial_turn_history(
                self.turns, agent_role, agent_id, repo_url
            )
            _save_turns(repo_url, agent_role, agent_id, self.turns)

        # 2.5) load per‐conversation metadata from DB (or start empty)
        self.metadata: Dict[str, Any] = load_conversation_metadata(
            repo_url, agent_role, agent_id
        ) or {}

        # 3) record LRU timestamp
        TurnHistory._lru[self._key] = time.time()

    @classmethod
    def get(cls,
            agent_role: str,
            agent_id:   str,
            repo_url:   str) -> "TurnHistory":
        """
        Retrieve or create the TurnHistory for (agent_role, agent_id, repo_url).
        Enforces an LRU‐based cap on the number of cached histories.
        """
        key = (agent_role, agent_id, repo_url)
        inst = cls._instances.get(key)
        if inst is None:
            inst = TurnHistory(agent_role, agent_id, repo_url)
            cls._instances[key] = inst

        # refresh LRU timestamp
        cls._lru[key] = time.time()

        # evict least recently used if over capacity
        while len(cls._instances) > MAX_TURNS_LISTS_IN_MEMORY:
            oldest = min(cls._lru, key=cls._lru.get)
            cls._instances.pop(oldest, None)
            cls._lru.pop(oldest, None)

        return inst

    def save(self) -> None:
        """ Persist the in‐memory history and metadata to SQLite. """
        _save_turns(
            self.repo_url,
            self.agent_role,
            self.agent_id,
            self.turns
        )
        # persist conversation‐level metadata
        save_conversation_metadata(
            self.repo_url,
            self.agent_role,
            self.agent_id,
            self.metadata
        )

    def add_turn(self, turn: UnifiedTurn) -> None:
        """
        Append a new turn:
          1) assign a monotonic turn ID
          2) append to in‐memory list
          3) persist to SQLite
          4) update agent_state
          5) apply tool filters → update metadata
          6) persist metadata
        """
        # 1) determine next turn ID
        last_idx, _ = load_state(
            self.repo_url, self.agent_role, self.agent_id
        )
        max_existing = max(
            (ut.turn_meta.get("turn", -1) for ut in self.turns),
            default=-1
        )
        if last_idx < max_existing:
            last_idx = max_existing
        new_idx = last_idx + 1

        # 2) append to in‐memory list
        turn.turn_meta["turn"] = new_idx
        self.turns.append(turn)

        # 3) apply any registered tool→metadata filters
        apply_tool_filters(turn, self.metadata)

        # 4) persist turns
        _save_turns(
            self.repo_url,
            self.agent_role,
            self.agent_id,
            self.turns
        )

        # 5) persist agent state
        save_state(
            self.repo_url,
            self.agent_role,
            self.agent_id,
            last_turn_idx=new_idx,
            last_message_id=None,
        )

        # 6) persist updated conversation‐level metadata
        save_conversation_metadata(
            self.repo_url,
            self.agent_role,
            self.agent_id,
            self.metadata
        )

        # refresh LRU
        TurnHistory._lru[self._key] = time.time()

    def remove_turn(self, turn_index: int) -> None:
        """
        Delete a single turn by its immutable turn_idx, then persist.
        """
        for i, ut in enumerate(self.turns):
            if ut.turn_meta.get("turn") == turn_index:
                self.turns.pop(i)
                break
        else:
            raise KeyError(f"Turn {turn_index} not found in history")

        _save_turns(
            self.repo_url,
            self.agent_role,
            self.agent_id,
            self.turns
        )
        TurnHistory._lru[self._key] = time.time()

    def delete_all(self) -> None:
        """
        Remove this agent/repo/task's entire turn history from memory and SQLite.
        """
        _delete_turns(
            self.repo_url,
            self.agent_role,
            self.agent_id
        )
        TurnHistory._instances.pop(self._key, None)
        TurnHistory._lru.pop(self._key, None)

    def query(
        self,
        limit:     int                 = 50,
        offset:    int                 = 0,
        status:    Optional[str]       = None,
        tool_name: Optional[str]       = None,
        deleted:   Optional[bool]      = None,
        sort:      Optional[List[str]] = None,
    ) -> List[UnifiedTurn]:
        """
        Raw SQL‐backed, pageable/filterable query (bypasses in‐memory cache).
        """
        return _query_turns(
            repo_url=self.repo_url,
            agent_role=self.agent_role,
            agent_id=self.agent_id,
            limit=limit, offset=offset,
            status=status, tool_name=tool_name,
            deleted=deleted, sort=sort,
        )

    # ------------------------------------------------------------------------
    # Conversation‐level metadata accessors
    # ------------------------------------------------------------------------

    def get_metadata(self) -> Dict[str, Any]:
        """Return the entire metadata dict for this conversation."""
        return self.metadata

    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Replace the metadata dict wholesale."""
        self.metadata = metadata

    def update_metadata(self, key: str, value: Any) -> None:
        """Set one key/value in the metadata."""
        self.metadata[key] = value

    def clear_metadata(self) -> None:
        """Remove all metadata entries."""
        self.metadata.clear()


# ------------------------------------------------------------------------
# Free‐function wrappers for turns list
# ------------------------------------------------------------------------

def get_turns_list(
    agent_role: Optional[str] = None,
    agent_id:   Optional[str] = None,
    repo_url:   Optional[str] = None
) -> List[UnifiedTurn]:
    if not (agent_role and agent_id and repo_url):
        # defer import to avoid circular dependency
        from modules.agents_running import get_current_agent_tuple as get_current_agent
        agent_role, agent_id, repo_url = get_current_agent()
    return TurnHistory.get(agent_role, agent_id, repo_url).turns


def add_turn_to_list(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
    turn:       UnifiedTurn
) -> None:
    TurnHistory.get(agent_role, agent_id, repo_url).add_turn(turn)


def save_turns_list(
    agent_role: str,
    agent_id:   str,
    repo_url:   str
) -> None:
    TurnHistory.get(agent_role, agent_id, repo_url).save()


def remove_turn_from_list(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
    turn_index: int
) -> None:
    TurnHistory.get(agent_role, agent_id, repo_url).remove_turn(turn_index)


def delete_turns_list(
    agent_role: str,
    agent_id:   str,
    repo_url:   str
) -> None:
    TurnHistory.get(agent_role, agent_id, repo_url).delete_all()


def query_turns_list(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
    limit:      int                 = 50,
    offset:     int                 = 0,
    status:     Optional[str]       = None,
    tool_name:  Optional[str]       = None,
    deleted:    Optional[bool]      = None,
    sort:       Optional[List[str]] = None,
) -> List[UnifiedTurn]:
    return TurnHistory.get(agent_role, agent_id, repo_url).query(
        limit=limit, offset=offset,
        status=status, tool_name=tool_name,
        deleted=deleted, sort=sort,
    )


# ------------------------------------------------------------------------
# Free‐function wrappers for conversation metadata
# ------------------------------------------------------------------------

def get_turns_metadata(
    agent_role: Optional[str] = None,
    agent_id:   Optional[str] = None,
    repo_url:   Optional[str] = None
) -> Dict[str, Any]:
    """
    Return the metadata dict for this conversation.
    """
    if not (agent_role and agent_id and repo_url):
        # defer import to avoid circular dependency
        from modules.agents_running import get_current_agent_tuple as get_current_agent
        agent_role, agent_id, repo_url = get_current_agent()
    return TurnHistory.get(agent_role, agent_id, repo_url).get_metadata()


def set_turns_metadata(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
    metadata:   Dict[str, Any]
) -> None:
    """
    Overwrite the entire metadata dict for this conversation.
    """
    TurnHistory.get(agent_role, agent_id, repo_url).set_metadata(metadata)


def update_turns_metadata(
    agent_role: str,
    agent_id:   str,
    repo_url:   str,
    key:        str,
    value:      Any
) -> None:
    """
    Set one metadata key/value on this conversation.
    """
    TurnHistory.get(agent_role, agent_id, repo_url).update_metadata(key, value)


def clear_turns_metadata(
    agent_role: str,
    agent_id:   str,
    repo_url:   str
) -> None:
    """
    Remove all metadata from this conversation (in‐memory only).
    """
    TurnHistory.get(agent_role, agent_id, repo_url).clear_metadata()


def clear_turns_for_agent(
    agent_role: str,
    agent_id:   str,
    repo_url:   str
) -> None:
    try:
        _delete_turns(repo_url, agent_role, agent_id)
    except Exception as e:
        logger.warning(
            "clear_turns_for_agent(%r,%r,%r) failed: %s",
            agent_role, agent_id, repo_url, e
        )
