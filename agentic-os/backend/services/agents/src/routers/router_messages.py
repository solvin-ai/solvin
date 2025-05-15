# routers/router_messages.py

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Union

from modules.messages_list import get_messages_list, get_message_by_id, append_messages
from modules.turns_list    import get_turns_list, delete_turns_list
from modules.db_state      import delete_state

router = APIRouter(
    prefix="/messages",
    tags=["Messages"],
)

class MessageAddRequest(BaseModel):
    agent_role: str
    agent_id:   str
    repo_url:   str
    role:       str
    content:    Union[str, List[str]]

class BroadcastRequest(BaseModel):
    agent_roles: List[str]
    messages:    Union[List[str], str]
    repo_url:    str

@router.post("/add")
def add_message_endpoint(
    payload: MessageAddRequest = Body(
        ...,
        examples={
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
        }
    )
) -> Dict[str, Any]:
    """
    POST /messages/add
    body: { agent_role, agent_id, repo_url, role, content }
    Appends one or more user/system messages as a new turn. Does not invoke LLM or tools.
    """
    result = append_messages(
        agent_role=payload.agent_role,
        agent_id=payload.agent_id,
        repo_url=payload.repo_url,
        role=payload.role,
        messages=payload.content
    )
    return {"data": result, "meta": None, "errors": []}

@router.get("/list")
def list_messages_endpoint(
    agent_role: str           = Query(..., description="Agent role"),
    agent_id:   str           = Query(..., alias="agent_id", description="Running-agent ID"),
    repo_url:   str           = Query(..., description="Repository URL"),
    role:       Optional[str] = Query(None, description="Filter by message role"),
    turn_id:    Optional[int] = Query(None, description="Filter by turn number"),
) -> Dict[str, Any]:
    """
    GET /messages/list?agent_role=&agent_id=&repo_url=&[role=&turn_id=]
    Returns all messages (optionally filtered) for a given (role, id, repo, task).
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
    repo_url:   str = Query(..., description="Repository URL"),
    message_id: int = Query(..., description="Original message ID to retrieve"),
) -> Dict[str, Any]:
    """
    GET /messages/get?agent_role=&agent_id=&repo_url=&message_id=
    Fetch a single message by its original_message_id.
    """
    result = get_message_by_id(
        agent_role=agent_role,
        agent_id=agent_id,
        repo_url=repo_url,
        message_id=message_id
    )
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"data": result, "meta": None, "errors": []}

@router.delete("/remove")
def remove_message_endpoint(
    agent_role: str = Query(..., description="Agent role"),
    agent_id:   str = Query(..., alias="agent_id", description="Running-agent ID"),
    repo_url:   str = Query(..., description="Repository URL"),
    message_id: int = Query(..., description="Original message ID to delete"),
) -> Dict[str, Any]:
    """
    DELETE /messages/remove?agent_role=&agent_id=&repo_url=&message_id=
    Removes one message (and drops the turn entirely if it becomes empty).
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
            # if the turn has no messages left, remove it entirely
            if not turn.messages:
                history.pop(turn_idx)
            break

    if not found:
        raise HTTPException(status_code=404, detail="Message not found")

    return {"data": {"message": f"Deleted message {message_id}"}, "meta": None, "errors": []}

@router.post("/broadcast")
def broadcast_message_endpoint(
    payload: BroadcastRequest = Body(
        ...,
        examples={
            "default": {
                "summary": "Default Example",
                "value": {
                    "agent_roles": ["root", "worker"],
                    "messages":    ["Hello all"],
                    "repo_url":    "my_repo"
                }
            }
        }
    )
) -> Dict[str, Any]:
    """
    POST /messages/broadcast
    body: { agent_roles, messages, repo_url }
    Sends the same message(s) to each of the named agents within the given task.
    """
    from modules.messages_broadcast import broadcast_message_to_agents

    result = broadcast_message_to_agents(
        agent_roles=payload.agent_roles,
        messages=payload.messages,
        repo_url=payload.repo_url
    )
    return {"data": result, "meta": None, "errors": []}
