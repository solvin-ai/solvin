# routers/router_agents_clear.py

from fastapi import APIRouter, HTTPException, Query
from modules.db_agents import clear_agents_for_repo
from modules.agents_running import list_running_agents
from modules.db_state import delete_state

router = APIRouter(
    prefix="/agents",
    tags=["Agents"],
)

@router.delete("/clear_repo")
def clear_repo(
    repo_url: str = Query(..., description="Repository name")
):
    """
    RPC‐style:
      DELETE /agents/clear_repo?repo_url=<repo>
    Clears all running agents, resets turn/message counters,
    and clears the current‐agent pointer for the given repo.
    """
    try:
        # 1) Gather all running agents for this repo
        running = list_running_agents(repo_url)

        # 2) Reset per‐agent state (turn/message ID counters)
        for entry in running:
            delete_state(repo_url, entry["agent_role"], entry["agent_id"])

        # 3) Clear the running‐agent registry and current‐agent pointer
        clear_agents_for_repo(repo_url)

        # 4) Wrap in standard envelope
        payload = {"message": f"Repo '{repo_url}' cleared."}
        return {"data": payload, "meta": None, "errors": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
