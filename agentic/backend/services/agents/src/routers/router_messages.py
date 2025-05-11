# routers/router_messages.py

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Union

from modules.messages_list import get_messages_list, get_message_by_id, append_messages
from modules.turns_list    import delete_turns_list, get_turns_list
from modules.db_state      import delete_state
from modules.db_agents     import list_running_agents as db_list_running_agents, list_all_repo_urls

router = APIRouter(
    prefix="/messages",
    tags=["Messages"],
)

class MessageAddRequest(BaseModel):
    agent_role: str
    agent_id:   str         # alias for agent_id
    repo_url:   str
    role:       str
    content:    Union[str, List[str]]

class BroadcastRequest(BaseModel):
    agent_roles: List[str]
    messages:    Union[List[str], str]
    repo_url:    str

@router.post("/add")
def add_message_endpoint(
    payload: MessageAddRequest = Body(..., examples={
        "default": {
            "summary": "Default Example",
            "value": {
                "agent_role": "root",
                "agent_id":   "001",
                "repo_url":   "my_repo",
                "role":       "user",
                "content":    "Hello!"
            }
        }
    })
) -> Dict[str, Any]:
    """
    RPC‐style:
      POST /messages/add
      body: { agent_role, agent_id, repo_url, role, content }
    Only persists the new message(s) as a single turn.
    Does NOT invoke any LLM or tool execution.
    """
    result = append_messages(
        agent_role=payload.agent_role,
        agent_id=payload.agent_id,
        role=payload.role,
        messages=payload.content,
        repo_url=payload.repo_url
    )
    return {"data": result, "meta": None, "errors": []}

@router.get("/list")
def list_messages_endpoint(
    agent_role: str           = Query(..., description="Agent role"),
    agent_id:   str           = Query(..., alias="agent_id", description="Running-agent ID"),
    repo_url:   str           = Query(..., description="Repository name"),
    role:       Optional[str] = Query(None, description="Filter by message role"),
    turn_id:    Optional[int] = Query(None, description="Filter by turn number"),
) -> Dict[str, Any]:
    """
    RPC‐style:
      GET /messages/list?agent_role=…&agent_id=…&repo_url=…[&role=…&turn_id=…]
    """
    result = get_messages_list(
        agent_role=agent_role,
        agent_id=agent_id,
        repo_url=repo_url,
        role=role,
        turn_id=turn_id,
    )
    return {"data": result, "meta": None, "errors": []}

@router.get("/get")
def get_message_endpoint(
    agent_role: str = Query(..., description="Agent role"),
    agent_id:   str = Query(..., alias="agent_id", description="Running-agent ID"),
    repo_url:   str = Query(..., description="Repository name"),
    message_id: int = Query(..., description="Message ID to retrieve"),
) -> Dict[str, Any]:
    """
    RPC‐style:
      GET /messages/get?agent_role=…&agent_id=…&repo_url=…&message_id=…
    """
    result = get_message_by_id(agent_role, agent_id, repo_url, message_id)
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"data": result, "meta": None, "errors": []}

@router.delete("/remove")
def remove_message_endpoint(
    agent_role: str = Query(..., description="Agent role"),
    agent_id:   str = Query(..., alias="agent_id", description="Running-agent ID"),
    repo_url:   str = Query(..., description="Repository name"),
    message_id: int = Query(..., description="Message ID to delete"),
) -> Dict[str, Any]:
    """
    RPC‐style:
      DELETE /messages/remove?agent_role=…&agent_id=…&repo_url=…&message_id=…
    Removes one message (and drops the turn if it becomes empty).
    """
    history = get_turns_list(agent_role, agent_id, repo_url)
    found = False

    for turn_idx, turn in enumerate(history):
        for role_name, msg in list(turn.messages.items()):
            if msg["meta"].get("original_message_id") == message_id:
                found = True
                del turn.messages[role_name]
                break
        if found:
            # if the turn is now empty, remove it entirely
            if not turn.messages:
                history.pop(turn_idx)
            break

    if not found:
        raise HTTPException(status_code=404, detail="Message not found")

    payload = {"message": f"Deleted message {message_id}"}
    return {"data": payload, "meta": None, "errors": []}

@router.delete("/remove_all")
def remove_all_messages_endpoint(
    agent_role: str = Query(..., description="Agent role"),
    agent_id:   str = Query(..., alias="agent_id", description="Running-agent ID"),
    repo_url:   str = Query(..., description="Repository name"),
) -> Dict[str, Any]:
    """
    RPC‐style:
      DELETE /messages/remove_all?agent_role=…&agent_id=…&repo_url=…
    Deletes all turns/messages and resets the ID counters.
    """
    # 1) delete all stored turns & messages
    delete_turns_list(agent_role, agent_id, repo_url)

    # 2) reset the turn/message ID counters
    delete_state(repo_url, agent_role, agent_id)

    payload = {
        "message": f"Deleted all messages for {agent_role}/{agent_id} in repo '{repo_url}'"
    }
    return {"data": payload, "meta": None, "errors": []}

@router.post("/broadcast")
def broadcast_message_endpoint(
    payload: BroadcastRequest = Body(..., examples={
        "default": {
            "summary": "Default Example",
            "value": {
                "agent_roles": ["root", "worker"],
                "messages":    ["Hello all"],
                "repo_url":   "my_repo"
            }
        }
    })
) -> Dict[str, Any]:
    """
    RPC‐style:
      POST /messages/broadcast
      body: { agent_roles, messages, repo_url }
    """
    from modules.messages_broadcast import broadcast_message_to_agents

    result = broadcast_message_to_agents(
        payload.agent_roles,
        payload.messages,
        repo_url=payload.repo_url
    )
    return {"data": result, "meta": None, "errors": []}

@router.delete("/clear")
def clear_history_endpoint(
    repo_url:   str = Query("*", description="Repo URL or '*'"),
    agent_role: str = Query("*", description="Agent role or '*'"),
    agent_id:   str = Query("*", description="Agent ID or '*'"),
) -> Dict[str, Any]:
    """
    DELETE /messages/clear?repo_url=&agent_role=&agent_id=
    Deletes all turns & messages (and resets counters) matching the filters.
    '*' is a wildcard at any level.
    """
    cleared: List[str] = []

    # 1) pick repos
    repos = [repo_url] if repo_url != "*" else list_all_repo_urls()

    for repo in repos:
        # 2) pick roles
        rows = db_list_running_agents(repo)
        roles = (
            {r["agent_role"] for r in rows}
            if agent_role == "*"
            else {agent_role}
        )

        for role in roles:
            # 3) pick IDs
            ids = (
                {r["agent_id"] for r in rows if r["agent_role"] == role}
                if agent_id == "*"
                else {agent_id}
            )

            for aid in ids:
                # 4) actually clear
                delete_turns_list(role, aid, repo)
                delete_state(repo, role, aid)
                cleared.append(f"{repo} | {role}:{aid}")

    if not cleared:
        raise HTTPException(status_code=404, detail="No matching history entries found")

    return {"data": {"cleared": cleared}, "meta": None, "errors": []}
