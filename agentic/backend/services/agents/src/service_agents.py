# service_agents.py

import threading
import time

from fastapi import FastAPI, Request
import uvicorn

from shared.config import config
from shared.logger import logger
from shared.client_repos import ReposClient, ReposClientError
from requests.exceptions import ReadTimeout, ConnectionError as ReqConnectionError

from modules.db import init_db
from modules.agents_running import seed_root_agent
from modules.agent_context import set_current_agent
from modules.run_to_completion import run_to_completion
from modules.agents_tasks import fetch_task_prompt

# -------------------------------------------------------------------
# Service metadata & API versioning
# -------------------------------------------------------------------
SERVICE_NAME    = "service_agents"
SERVICE_VERSION = "3.0.0"
config["SERVICE_NAME"]   = SERVICE_NAME
config["SERVICE_VERSION"] = SERVICE_VERSION

API_VERSION = "v1"
API_PREFIX  = f"/api/{API_VERSION}"

# -------------------------------------------------------------------
# Feature flags / config switches
# -------------------------------------------------------------------
DISABLE_REPO_CLAIM = config.get("DISABLE_REPO_CLAIM", False)

# -------------------------------------------------------------------
# Global state
# -------------------------------------------------------------------
API_REQUESTS       = 0
_PROCESSING_THREAD = None

# track the currently claimed repo for status & readiness endpoints
CLAIMED_REPO_META = {
    "repo_url":   None,
    "repo_name":  None,
    "repo_owner": None,
}

# expose counters & claimed‐repo meta via config
config["api_requests"]      = lambda: API_REQUESTS
config["claimed_repo_meta"] = lambda: CLAIMED_REPO_META

# -------------------------------------------------------------------
# FastAPI setup
# -------------------------------------------------------------------
app = FastAPI(
    title="Agentic Service",
    description="Service that wraps message-centric conversation, registry, and agent management.",
    version=SERVICE_VERSION,
)

@app.middleware("http")
async def _count_api_requests(request: Request, call_next):
    global API_REQUESTS
    API_REQUESTS += 1
    return await call_next(request)

@app.get("/health")
def raw_health():
    return {"data": {"status": "ok", "reason": "running"}, "meta": None, "errors": []}

# -------------------------------------------------------------------
# Repository processing
# -------------------------------------------------------------------

def _process_repo(
    agent_id:    str,
    repo_url:    str,
    repo_owner:  str,
    repo_name:   str,
    user_prompt: str
) -> None:
    """
    Background thread entrypoint: runs the 'root' agent through to completion,
    then calls the GitHub complete endpoint if successful.  When done, clears
    CLAIMED_REPO_META so /ready and /status will reflect no active claim.
    """
    global _PROCESSING_THREAD
    try:
        result = run_to_completion(
            agent_role="root",
            agent_id=agent_id,
            repo_url=repo_url,
            repo_owner=repo_owner,
            repo_name=repo_name,
            user_prompt=user_prompt,
        )
        status = result.get("status")
        if status == "success":
            logger.info(f"Repo {repo_url!r} succeeded; calling complete endpoint")
            try:
                client = ReposClient()
                client.complete_repo(repo_url)
                logger.info(f"Marked {repo_url!r} as complete")
            except Exception as e:
                logger.error(f"Failed to complete {repo_url!r}: {e}", exc_info=True)
        else:
            logger.warning(f"Root agent for {repo_url!r} finished with status={status}")
    finally:
        # clear the in‐flight claim
        CLAIMED_REPO_META["repo_url"]   = None
        CLAIMED_REPO_META["repo_name"]  = None
        CLAIMED_REPO_META["repo_owner"] = None

        _PROCESSING_THREAD = None
        logger.info(f"Cleared processing thread and claim for {repo_url!r}")

def _claim_repo_loop():
    """
    Continuously claims repos, seeds the root agent, and spins off
    _process_repo threads with explicit owner/name context.
    """
    global _PROCESSING_THREAD
    client = ReposClient()

    while True:
        # Wait if still processing
        if _PROCESSING_THREAD and _PROCESSING_THREAD.is_alive():
            time.sleep(2)
            continue

        # Attempt to claim a repo (blocking up to timeout)
        try:
            claim = client.claim_repo_blocking(timeout=30.0)
        except ReadTimeout:
            logger.debug("No repo claim yet; retrying in 5s")
            time.sleep(5)
            continue
        except ReqConnectionError as e:
            logger.warning(f"Connection error during repo claim: {e}; retrying in 5s")
            time.sleep(5)
            continue
        except ReposClientError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.debug("No repository to claim; retrying in 5s")
                time.sleep(5)
                continue
            logger.error(f"Error claiming repository: {e}", exc_info=True)
            time.sleep(5)
            continue
        except Exception as e:
            logger.error(f"Unexpected error in claim loop: {e}", exc_info=True)
            time.sleep(5)
            continue

        repo_url = claim.get("repo_url")
        if not repo_url:
            logger.debug("Empty claim returned; retrying in 5s")
            time.sleep(5)
            continue

        logger.info(f"Claimed repository: {repo_url!r}")

        # Immediately fetch full metadata
        try:
            full_info = client.get_repo_info(repo_url)
        except Exception as e:
            logger.error(f"Failed to fetch full repo_info for {repo_url!r}: {e}", exc_info=True)
            # clear in‐flight claim and retry later
            CLAIMED_REPO_META["repo_url"]   = None
            CLAIMED_REPO_META["repo_name"]  = None
            CLAIMED_REPO_META["repo_owner"] = None
            continue

        # merge full_info fields into our claim dict
        claim.update(full_info)

        # Seed the root agent (populates turn-0)
        seeded_id = seed_root_agent(repo_url)
        agent_id  = seeded_id or "001"
        logger.info(f"Using root agent id {agent_id!r} for {repo_url!r}")

        # Extract owner/name from merged info
        repo_owner = claim.get("repo_owner")
        repo_name  = claim.get("repo_name")

        # record the claim for status/readiness endpoints
        CLAIMED_REPO_META["repo_url"]   = repo_url
        CLAIMED_REPO_META["repo_name"]  = repo_name
        CLAIMED_REPO_META["repo_owner"] = repo_owner
        # you can also stash other metadata if desired:
        # CLAIMED_REPO_META["source_file_count"] = claim.get("source_file_count")
        # CLAIMED_REPO_META["total_loc"]         = claim.get("total_loc")
        # CLAIMED_REPO_META["metadata"]          = claim.get("metadata", {})

        # set current-agent context for downstream turns
        set_current_agent("root", agent_id, repo_url)

        # Optionally include a TASK_NAME prompt
        task_name   = config.get("TASK_NAME", "").strip()
        user_prompt = ""
        if task_name:
            raw_prompt = fetch_task_prompt(task_name) or ""
            user_prompt = raw_prompt
            logger.info(f"Fetched task_prompt '{task_name}': {user_prompt!r}")

        # Launch the processing thread
        _PROCESSING_THREAD = threading.Thread(
            target=_process_repo,
            args=(agent_id, repo_url, repo_owner, repo_name, user_prompt),
            daemon=True,
        )
        _PROCESSING_THREAD.start()
        logger.info(f"Started processing thread for {repo_url!r}")

        # brief pause before next claim
        time.sleep(5)

# -------------------------------------------------------------------
# Startup event
# -------------------------------------------------------------------
@app.on_event("startup")
def _on_startup():
    init_db()
    logger.info("DB schema ensured (tables created if missing).")

    if DISABLE_REPO_CLAIM:
        logger.info("Repo-claim loop disabled by config.")
    else:
        t = threading.Thread(target=_claim_repo_loop, daemon=True)
        t.start()
        logger.info("Started background repo-claim thread.")

# -------------------------------------------------------------------
# Include routers under versioned prefix
# -------------------------------------------------------------------
from routers.router_health_status_ready import router as router_health_status_ready
from routers.router_agents_registry     import router as router_agents_registry
from routers.router_agents_running      import router as router_agents_running
from routers.router_agents_clear        import router as router_agents_clear
from routers.router_messages            import router as router_messages
from routers.router_llm                 import router as router_llm
from routers.router_turns               import router as router_turns

app.include_router(router_health_status_ready, prefix=API_PREFIX)
app.include_router(router_agents_registry,     prefix=API_PREFIX)
app.include_router(router_agents_running,      prefix=API_PREFIX)
app.include_router(router_agents_clear,        prefix=API_PREFIX)
app.include_router(router_messages,            prefix=API_PREFIX)
app.include_router(router_llm,                 prefix=API_PREFIX)
app.include_router(router_turns,               prefix=API_PREFIX)

if __name__ == "__main__":
    uvicorn.run(f"{SERVICE_NAME}:app", host="0.0.0.0", port=8000, reload=True)
