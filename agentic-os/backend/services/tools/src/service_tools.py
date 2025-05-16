# service_tools.py

import time
import asyncio

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler

from shared.config import config
from shared.logger import logger

# registry initialization
from modules.tools_registry import initialize_global_registry

# JetStream init & responder
from modules.tools_jetstream_init import get_jetstream
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
# FastAPI app & custom exception handler
# -------------------------------------------------------------------
app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description="Executes dynamic tools with per-repo environments."
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Catch and log any Pydantic validation errors so you can see
    the raw body and the validation details in your logs.
    """
    body = await request.body()
    logger.error(
        "ValidationError on %s %s\nBody: %s\nErrors: %s",
        request.method, request.url.path,
        body.decode("utf8", "replace"),
        exc.errors()
    )
    return await request_validation_exception_handler(request, exc)

# -------------------------------------------------------------------
# HTTP middleware
# -------------------------------------------------------------------
@app.middleware("http")
async def count_requests(request: Request, call_next):
    global API_REQUESTS
    API_REQUESTS += 1
    return await call_next(request)

@app.middleware("http")
async def log_request_times(request: Request, call_next):
    t0 = time.monotonic()
    response = await call_next(request)
    elapsed = (time.monotonic() - t0) * 1000
    logger.debug("HTTP %s %s completed in %.1fms", request.method, request.url.path, elapsed)
    return response

# -------------------------------------------------------------------
# start & stop the JetStream responder in the same event loop
# -------------------------------------------------------------------
_responder_task: asyncio.Task | None = None

@app.on_event("startup")
async def _start_jetstream_responder():
    """
    1) Warm up the JetStream client (connect & ensure stream exists)
    2) Launch the request-to-response responder as a background task.
    """
    global _responder_task

    logger.info("🚀 [startup] _start_jetstream_responder() firing")

    # 1) Warm-up
    logger.info("Warming up JetStream client…")
    t0 = time.monotonic()
    try:
        await get_jetstream()
        elapsed = (time.monotonic() - t0) * 1000
        logger.info("✅ [startup] get_jetstream() completed in %.1fms", elapsed)
    except Exception as e:
        logger.error("❌ JetStream warm-up failed: %s", e, exc_info=True)
        raise

    # 2) Start responder
    logger.info("Starting JetStream responder task…")
    _responder_task = asyncio.create_task(run_responder())
    logger.info("✅ [startup] run_responder() scheduled")

    # slight delay to let the responder subscribe
    await asyncio.sleep(0.1)
    logger.info("✅ JetStream responder started.")

@app.on_event("shutdown")
async def _stop_jetstream_responder():
    """
    Cancel the JetStream responder task cleanly on shutdown.
    """
    global _responder_task
    if _responder_task:
        logger.info("Shutting down JetStream responder…")
        _responder_task.cancel()
        try:
            await _responder_task
        except asyncio.CancelledError:
            logger.info("JetStream responder cancelled.")
        _responder_task = None

# -------------------------------------------------------------------
# mount routers
# -------------------------------------------------------------------
from routers.router_health   import router as health_router
from routers.router_tools    import router as tools_router
from routers.router_execute  import router as execute_router

app.include_router(health_router,  prefix="")
app.include_router(health_router,  prefix=API_PREFIX)
app.include_router(tools_router,   prefix=API_PREFIX)
app.include_router(execute_router, prefix=API_PREFIX)

# -------------------------------------------------------------------
# Uvicorn entrypoint
# -------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("service_tools:app", host="0.0.0.0", port=8001, reload=True)
