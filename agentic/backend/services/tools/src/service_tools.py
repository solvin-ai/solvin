# service_tools.py

import time
import asyncio
from fastapi import FastAPI, Request
from shared.config import config
from shared.logger import logger

# registry initialization
from modules.tools_registry import initialize_global_registry

# JetStream responder
from modules.tools_jetstream_sub import run_responder

# -------------------------------------------------------------------
# service metadata & versioning
# -------------------------------------------------------------------
SERVICE_NAME    = "service_tools"
SERVICE_VERSION = "3.0.0"
config["SERVICE_NAME"] = SERVICE_NAME

API_VERSION = "v1"
API_PREFIX  = f"/api/{API_VERSION}"

# -------------------------------------------------------------------
# runtime metrics
# -------------------------------------------------------------------
SERVICE_START_TIME = time.time()
API_REQUESTS       = 0
config["tools_api_requests"] = lambda: API_REQUESTS

# -------------------------------------------------------------------
# initialize the global tools registry before loading any routers
# -------------------------------------------------------------------
try:
    global_registry = initialize_global_registry()
    logger.info("Loaded %d tools into registry", len(global_registry))
except Exception as e:
    global_registry = {}
    logger.error("Failed to init tools registry: %s", e, exc_info=True)

# -------------------------------------------------------------------
# FastAPI app & middleware
# -------------------------------------------------------------------
app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description="Executes dynamic tools with per-repo environments."
)

@app.middleware("http")
async def count_requests(request: Request, call_next):
    global API_REQUESTS
    API_REQUESTS += 1
    return await call_next(request)

# -------------------------------------------------------------------
# start & stop the JetStream responder in the same event loop
# -------------------------------------------------------------------
_responder_task: asyncio.Task | None = None

@app.on_event("startup")
async def _start_jetstream_responder():
    """
    Launch the JetStream request-to-response responder
    as a background task on startup.
    """
    global _responder_task
    logger.info("Starting JetStream responder task...")
    _responder_task = asyncio.create_task(run_responder())
    # slight delay to let it connect
    await asyncio.sleep(0.1)
    logger.info("JetStream responder started.")

@app.on_event("shutdown")
async def _stop_jetstream_responder():
    """
    Cancel the responder task cleanly on shutdown.
    """
    global _responder_task
    if _responder_task:
        logger.info("Shutting down JetStream responder...")
        _responder_task.cancel()
        try:
            await _responder_task
        except asyncio.CancelledError:
            logger.info("JetStream responder cancelled.")
        _responder_task = None

# -------------------------------------------------------------------
# only now import & mount the routers
# -------------------------------------------------------------------
from routers.router_health   import router as health_router
from routers.router_tools    import router as tools_router
from routers.router_execute  import router as execute_router

app.include_router(health_router,  prefix=API_PREFIX)
app.include_router(tools_router,   prefix=API_PREFIX)
app.include_router(execute_router, prefix=API_PREFIX)

# -------------------------------------------------------------------
# Uvicorn entrypoint
# -------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("service_tools:app", host="0.0.0.0", port=8001, reload=True)
