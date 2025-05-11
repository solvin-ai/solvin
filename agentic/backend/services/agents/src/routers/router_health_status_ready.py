# routers/router_health_status_ready.py

from fastapi import APIRouter
import time
from shared.config import config

router = APIRouter(
    tags=["Health"],
)

# Record the application start time for uptime calculations
_service_start_time = time.time()


@router.get("/health")
def health_check():
    """
    Returns service liveness.
    If there's a claimed repo in flight, we're still 'running',
    otherwise we're 'ready' immediately.
    """
    claimed = config["claimed_repo_meta"]().get("repo_url")
    # We always return status "ok"; reason stays "running" per original behavior
    reason = "running"
    payload = {
        "status": reason,
        "reason": reason,
    }
    return {
        "data": payload,
        "meta": None,
        "errors": []
    }


@router.get("/ready")
def readiness_check():
    """
    Returns readiness: have we finished starting up / processing?
    """
    claimed = config["claimed_repo_meta"]().get("repo_url")
    ready = not bool(claimed)
    reason = "ready" if ready else "running"
    payload = {
        "ready": ready,
        "reason": reason,
    }
    return {
        "data": payload,
        "meta": None,
        "errors": []
    }


@router.get("/status")
def status_info():
    """
    Returns service metadata:
      • uptime
      • version
      • total API requests served
      • currently claimed repo (if any)
      • repo_state (running/ready)
    """
    uptime = int(time.time() - _service_start_time)
    claimed = config["claimed_repo_meta"]().get("repo_url")
    repo_state = "running" if claimed else "ready"
    payload = {
        "claimed_repo":   claimed,
        "repo_state":     repo_state,
        "uptime_seconds": uptime,
        "version":        config.get("SERVICE_VERSION"),
        "api_requests":   config["api_requests"](),
    }
    return {
        "data": payload,
        "meta": None,
        "errors": []
    }
