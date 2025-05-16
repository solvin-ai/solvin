# service_agents.py
# service_agents.py

import os
import threading
import time

from fastapi import FastAPI, Request
import uvicorn

from shared.config import config
from shared.logger import logger
from shared.client_repos import ReposClient, ReposClientError
from requests.exceptions import ReadTimeout, ConnectionError as ReqConnectionError

from modules.db import init_db
from modules.run_agent_task import run_agent_task
from modules.tasks import fetch_task_prompt
from modules.agents_running import seed_agent  # <-- import seed_agent

# -------------------------------------------------------------------
# Tool registry cache (starts on startup, refreshes periodically)
# -------------------------------------------------------------------
from modules.tool_registry_cache import (
    start_tool_registry_cache_thread,
    get_tools_registry,
    stop_tool_registry_cache_thread,
)

# -------------------------------------------------------------------
# Optional hard-halt on uncaught thread exceptions
# -------------------------------------------------------------------
ENABLE_EXCEPTION_HALT = os.environ.get("SOLVIN_EXCEPTION_HALT", "").lower() in ("1", "true", "yes")
if ENABLE_EXCEPTION_HALT:
    def _threading_excepthook(args: threading.ExceptHookArgs):
        """
        Called whenever a Thread terminates with an uncaught exception.
        Logs the exception and immediately halts the process.
        """
        logger.error(
            f"Uncaught exception in thread {args.thread.name!r}: {args.exc_value!r}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
        )
        os._exit(1)

    threading.excepthook = _threading_excepthook
    logger.info("Enabled SOLVIN_EXCEPTION_HALT: unhandled thread exceptions will os._exit(1)")

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

CLAIMED_REPO_META = {
    "repo_url":   None,
    "repo_name":  None,
    "repo_owner": None,
}

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
    then calls the GitHub complete endpoint if successful. When done, clears
    CLAIMED_REPO_META so /ready and /status will reflect no active claim.
    """
    global _PROCESSING_THREAD
    try:
        result = run_agent_task(
            agent_role="root",
            repo_url=repo_url,
            user_prompt=user_prompt,
            agent_id=agent_id,
            repo_owner=repo_owner,
            repo_name=repo_name,
        )

        if result.get("success"):
            logger.info(f"Repo {repo_url!r} succeeded; calling complete endpoint")
            try:
                client = ReposClient()
                client.complete_repo(repo_url)
                logger.info(f"Marked {repo_url!r} as complete")
            except Exception as e:
                logger.error(f"Failed to complete {repo_url!r}: {e}", exc_info=True)
                if ENABLE_EXCEPTION_HALT:
                    raise
        else:
            logger.warning(
                f"Root agent for {repo_url!r} failed; "
                f"task_result={result.get('task_result')!r}"
            )
    except Exception:
        logger.exception("Unhandled exception in _process_repo, aborting.")
        raise
    finally:
        # clear the in-flight claim
        CLAIMED_REPO_META["repo_url"]   = None
        CLAIMED_REPO_META["repo_name"]  = None
        CLAIMED_REPO_META["repo_owner"] = None

        _PROCESSING_THREAD = None
        logger.info(f"Cleared processing thread and claim for {repo_url!r}")

def _claim_repo_loop():
    """
    Continuously claims repos, seeds the root agent, and spins off
    _process_repo threads with explicit owner/name/context.
    """
    global _PROCESSING_THREAD
    client = ReposClient()

    try:
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
                # clear in-flight claim and retry later
                CLAIMED_REPO_META["repo_url"]   = None
                CLAIMED_REPO_META["repo_name"]  = None
                CLAIMED_REPO_META["repo_owner"] = None
                continue

            # merge full_info fields into our claim dict
            claim.update(full_info)

            # Pull TASK_NAME out of config (must be non-empty)
            task_name = config.get("TASK_NAME", "").strip()
            assert task_name, "TASK_NAME must be set in config"
            logger.info(f"Seeding root agent with TASK_NAME={task_name!r}")

            # ----------------------------------------------------------------
            # SEED ROOT AGENT directly (no run_agent_task), passing TASK_NAME
            # ----------------------------------------------------------------
            root_id = seed_agent(
                agent_role="root",
                repo_url=repo_url,
                agent_id="001",
                user_prompt=task_name,
            )
            logger.info(f"Seeded root agent id {root_id!r} for {repo_url!r}")

            # record claim state
            repo_owner = claim.get("repo_owner")
            repo_name  = claim.get("repo_name")
            CLAIMED_REPO_META["repo_url"]   = repo_url
            CLAIMED_REPO_META["repo_name"]  = repo_name
            CLAIMED_REPO_META["repo_owner"] = repo_owner

            # Now fetch the actual user prompt text
            user_prompt = fetch_task_prompt(task_name) or ""
            logger.info(f"Fetched task_prompt '{task_name}': {user_prompt!r}")

            # Launch the processing thread
            _PROCESSING_THREAD = threading.Thread(
                target=_process_repo,
                args=(root_id, repo_url, repo_owner, repo_name, user_prompt),
                daemon=True,
            )
            _PROCESSING_THREAD.start()
            logger.info(f"Started processing thread for {repo_url!r}")

            # brief pause before next claim
            time.sleep(5)

    except Exception:
        logger.exception("Unhandled exception in _claim_repo_loop, aborting.")
        raise

# -------------------------------------------------------------------
# Startup event
# -------------------------------------------------------------------
@app.on_event("startup")
def _on_startup():
    init_db()
    logger.info("DB schema ensured (tables created if missing).")

    # Start the background cache refresher for the tool registry
    start_tool_registry_cache_thread(refresh_interval=300)  # refresh every 5 minutes

    # Warm the registry immediately so first parse is fast
    reg = get_tools_registry()
    count = len(reg) if hasattr(reg, "__len__") else -1
    names = [
        e.get("name")
        for e in (reg.values() if isinstance(reg, dict) else reg)
        if isinstance(e, dict) and "name" in e
    ]
    logger.info("Warmed tool registry with %d entries: %s", count, names)

    if DISABLE_REPO_CLAIM:
        logger.info("Repo-claim loop disabled by config.")
    else:
        t = threading.Thread(target=_claim_repo_loop, daemon=True)
        t.start()
        logger.info("Started background repo-claim thread.")

# -------------------------------------------------------------------
# Shutdown event
# -------------------------------------------------------------------
@app.on_event("shutdown")
def _on_shutdown():
    stop_tool_registry_cache_thread()
    logger.info("Stopped tool registry refresh thread.")

# -------------------------------------------------------------------
# Include routers under versioned prefix
# -------------------------------------------------------------------
from routers.router_health_status_ready import router as router_health_status_ready
from routers.router_agents_registry     import router as router_agents_registry
from routers.router_agents_running      import router as router_agents_running
from routers.router_messages            import router as router_messages
from routers.router_llm                 import router as router_llm
from routers.router_turns               import router as router_turns

app.include_router(router_health_status_ready, prefix=API_PREFIX)
app.include_router(router_agents_registry,     prefix=API_PREFIX)
app.include_router(router_agents_running,      prefix=API_PREFIX)
app.include_router(router_messages,            prefix=API_PREFIX)
app.include_router(router_llm,                 prefix=API_PREFIX)
app.include_router(router_turns,               prefix=API_PREFIX)

if __name__ == "__main__":
    uvicorn.run(f"{SERVICE_NAME}:app", host="0.0.0.0", port=8000, reload=True)
