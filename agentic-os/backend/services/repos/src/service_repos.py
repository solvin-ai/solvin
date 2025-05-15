# service_repos.py

from shared.config import config
# -------------------------
SERVICE_NAME    = "service_repos"
SERVICE_VERSION = "3.0.0"
API_VERSION     = "v1"
API_PREFIX      = f"/api/{API_VERSION}"

config["SERVICE_NAME"] = SERVICE_NAME

import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

# import our routers
import routers.router_health   as health
import routers.router_info     as info
import routers.router_add      as add       # raw add endpoint
import routers.router_admit    as admit     # URL-based admit endpoint
import routers.router_delete   as delete
import routers.router_complete as complete
import routers.router_claim    as claim

from modules.routers_core import (
    init_db,
    refresh_repo_queue,
    unclaim_expired_task,
    register_sqlite_busy_handler,
)

# -------------------------
# service-level globals
# -------------------------
SERVICE_START_TIME = time.time()
API_REQUESTS       = 0
global_registry    = {}    # e.g. plugin/tool registry
#-------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize our SQLite schema
    init_db()

    # Start background tasks (skip in testing)
    if not config.get("TESTING", False):
        # refill the claim queue
        asyncio.create_task(refresh_repo_queue())
        # periodically un‐claim repos whose TTL has expired
        asyncio.create_task(unclaim_expired_task())

    yield


app = FastAPI(
    title    = SERVICE_NAME,
    version  = SERVICE_VERSION,
    lifespan = lifespan
)

# Translate sqlite3 “database is locked” → HTTP 503
register_sqlite_busy_handler(app)

# Stash globals on app.state for router_health
app.state.service_start_time = SERVICE_START_TIME
app.state.api_requests       = API_REQUESTS
app.state.service_version    = SERVICE_VERSION
app.state.global_registry    = global_registry

# Simple middleware to bump request counter
@app.middleware("http")
async def count_requests(request: Request, call_next):
    request.app.state.api_requests += 1
    return await call_next(request)

# Mount all routers
app.include_router(health.router,   prefix="") # Alias: expose /health directly
app.include_router(health.router,   prefix=API_PREFIX)
app.include_router(info.router,     prefix=API_PREFIX)
app.include_router(add.router,      prefix=API_PREFIX)
app.include_router(admit.router,    prefix=API_PREFIX)
app.include_router(delete.router,   prefix=API_PREFIX)
app.include_router(complete.router, prefix=API_PREFIX)
app.include_router(claim.router,    prefix=API_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(f"{SERVICE_NAME}:app", host="0.0.0.0", port=8002, reload=True)
