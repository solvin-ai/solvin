# routers/router_health.py

from fastapi import APIRouter
import time

from shared.logger import logger

from service_tools import (
    SERVICE_START_TIME,
    API_REQUESTS,
    SERVICE_VERSION,
    global_registry,
)

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness probe")
def health_check():
    try:
        return {"status": "ok", "data": {"status": "ok"}, "error": None}
    except Exception as e:
        logger.error("Unhandled exception in /health: %s", e, exc_info=True)
        return {"status": "error", "data": None, "error": {"code": None, "message": str(e)}}


@router.get("/", summary="Root health check")
def root_check():
    try:
        return {"status": "ok", "data": {"status": "ok"}, "error": None}
    except Exception as e:
        logger.error("Unhandled exception in /: %s", e, exc_info=True)
        return {"status": "error", "data": None, "error": {"code": None, "message": str(e)}}


@router.get("/ready", summary="Readiness probe")
def ready_check():
    try:
        return {"status": "ok", "data": {"status": "ready"}, "error": None}
    except Exception as e:
        logger.error("Unhandled exception in /ready: %s", e, exc_info=True)
        return {"status": "error", "data": None, "error": {"code": None, "message": str(e)}}


@router.get("/status", summary="Service status & metrics")
def status_check():
    try:
        uptime = int(time.time() - SERVICE_START_TIME)
        data = {
            "status": "ok",
            "requests": API_REQUESTS,
            "version": SERVICE_VERSION,
            "uptime_seconds": uptime,
            "tool_count": len(global_registry),
        }
        return {"status": "ok", "data": data, "error": None}
    except Exception as e:
        logger.error("Unhandled exception in /status: %s", e, exc_info=True)
        return {"status": "error", "data": None, "error": {"code": None, "message": str(e)}}