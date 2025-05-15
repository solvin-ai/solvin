# modules/messages_broadcast.py

from typing        import List, Union, Dict
from modules.agents_running import list_running_agents
from modules.messages_list   import append_messages

def broadcast_message_to_agents(
    agent_roles: List[str],
    messages:    Union[List[str], str],
    repo_url:    str
) -> Dict[str, Union[int, List[str]]]:
    """
    Broadcast one or multiple messages as a single 'user' turn to running agents
    in the given repo/task.

    If `agent_roles` is non‐empty, only agents whose role is in
    that list will receive the broadcast. If `agent_roles` is empty,
    broadcast to all running agents in the given repo/task.

    Args:
        agent_roles: List of agent role strings to match (empty ⇒ all).
        messages:    A string or list of string messages to broadcast.
        repo_url:    The repository context to scope the broadcast.

    Returns:
        dict: { "success_count": int, "errors": [str] }
    """
    roles_set     = set(agent_roles)
    # now scoped by repo_url
    running_agents = list_running_agents(repo_url=repo_url)

    success_count = 0
    error_list: List[str] = []

    for agent in running_agents:
        ar  = agent["agent_role"]
        aid = agent["agent_id"]
        # if roles_set is non‐empty, filter by roles; else allow all
        if roles_set and ar not in roles_set:
            continue
        try:
            append_messages(
                agent_role=ar,
                agent_id=aid,
                role="user",
                messages=messages,
                repo_url=repo_url
            )
            success_count += 1
        except Exception as ex:
            error_list.append(f"{ar}:{aid} - Exception: {ex}")

    return {"success_count": success_count, "errors": error_list}


if __name__ == "__main__":
    # Quick smoke‐test
    res = broadcast_message_to_agents(
        [],  # empty list ⇒ send to *all* agents
        ["Hello, world!", "Second broadcast"],
        repo_url="test_agents_running_repo"
    )
    print(res)
