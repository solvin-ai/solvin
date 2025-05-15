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
    Returns service liveness:
      • Always returns status="ok"
      • reason="running" if we have a claimed repo in flight, else "ready"
      • echoes back the claimed repo+task, if any
    """
    claimed_meta = config["claimed_repo_meta"]() or {}
    has_claimed = bool(claimed_meta.get("repo_url"))
    status = "ok"
    reason = "running" if has_claimed else "ready"
    payload = {
        "status":  status,
        "reason":  reason,
        "claimed": claimed_meta
    }
    return {
        "data":   payload,
        "meta":   None,
        "errors": []
    }


@router.get("/ready")
def readiness_check():
    """
    Returns readiness:
      • ready = False if there is a claimed repo/task still being processed
      • ready = True otherwise
      • echoes back the claimed repo+task, if any
    """
    claimed_meta = config["claimed_repo_meta"]() or {}
    has_claimed = bool(claimed_meta.get("repo_url"))
    ready = not has_claimed
    reason = "ready" if ready else "running"
    payload = {
        "ready":   ready,
        "reason":  reason,
        "claimed": claimed_meta
    }
    return {
        "data":   payload,
        "meta":   None,
        "errors": []
    }


@router.get("/status")
def status_info():
    """
    Returns service metadata:
      • claimed:   { repo_url } or {}  
      • repo_state: "running" if claimed, else "ready"  
      • uptime_seconds  
      • version  
      • api_requests  
    """
    uptime = int(time.time() - _service_start_time)
    claimed_meta = config["claimed_repo_meta"]() or {}
    has_claimed = bool(claimed_meta.get("repo_url"))
    repo_state = "running" if has_claimed else "ready"

    payload = {
        "claimed":        claimed_meta,
        "repo_state":     repo_state,
        "uptime_seconds": uptime,
        "version":        config.get("SERVICE_VERSION"),
        "api_requests":   config["api_requests"](),
    }
    return {
        "data":   payload,
        "meta":   None,
        "errors": []
    }
