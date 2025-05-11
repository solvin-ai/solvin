# service_configs.py

import os
import re
from threading import RLock
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel
from omegaconf import OmegaConf

SERVICE_NAME = "service_configs"
SERVICE_VERSION = "3.0.0"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "data", "config.yaml")
CONFIG_LOCK = RLock()

app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description="Global & service-scoped config storage (YAML + OmegaConf)"
)

def _read_cleaned_yaml() -> str:
    raw = open(CONFIG_FILE, "r").read()
    # strip out any !required tags before parsing
    return re.sub(r"!required\s+", "", raw)

def load_config(resolve: bool = True) -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            cleaned = _read_cleaned_yaml()
            conf = OmegaConf.create(cleaned)
            data = OmegaConf.to_container(conf, resolve=resolve) or {}
            if not isinstance(data, dict):
                raise HTTPException(500, "Config root must be a dict.")
            return data
        except Exception as e:
            raise HTTPException(500, f"Error loading config: {e}")
    return {}

def save_config(data: dict):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with CONFIG_LOCK:
        try:
            conf = OmegaConf.create(data)
            with open(CONFIG_FILE, "w") as f:
                OmegaConf.save(conf, f)
        except Exception as e:
            raise HTTPException(500, f"Error saving config: {e}")

def get_section(data: dict, scope: str, create_if_missing: bool = False) -> Optional[dict]:
    """
    Drill into nested dict for a dotted scope (e.g. "service.agents") or "global".
    """
    if not isinstance(data, dict):
        return None
    path = scope.split(".") if scope and scope != "global" else [scope or "global"]
    curr = data
    for part in path:
        if part not in curr:
            if create_if_missing:
                curr[part] = {}
            else:
                return None
        curr = curr[part]
        if not isinstance(curr, dict) and part != path[-1]:
            return None
    return curr

def _prune_empty_scope(data: dict, scope: str):
    """
    If scope != 'global' and that section is empty, delete it from its parent.
    E.g. for scope="foo.bar", remove data['foo']['bar'] if {}.
    """
    if scope == "global":
        return
    section = get_section(data, scope)
    if section is None or section:
        return  # either not present or not empty
    parts = scope.split(".")
    # top‐level non-global
    if len(parts) == 1:
        data.pop(parts[0], None)
    else:
        parent_scope = ".".join(parts[:-1])
        parent = get_section(data, parent_scope)
        if parent and parts[-1] in parent:
            parent.pop(parts[-1], None)

@app.on_event("startup")
def _validate_required_keys():
    """
    Scan for !required in the YAML, then after loading/resolving
    ensure each required path is present and non-null.
    """
    try:
        raw = open(CONFIG_FILE, "r").readlines()
    except FileNotFoundError:
        return

    # collect required dotted paths
    required: List[str] = []
    stack: List[tuple[int, str]] = []
    for line in raw:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        # pop same or deeper indents
        while stack and stack[-1][0] >= indent:
            stack.pop()
        m = re.match(r'\s*([^:\s][^:]*):', line)
        if m:
            stack.append((indent, m.group(1)))
        if "!required" in line:
            required.append(".".join(k for _, k in stack))

    # load + resolve
    try:
        cleaned = _read_cleaned_yaml()
        conf = OmegaConf.create(cleaned)
        full = OmegaConf.to_container(conf, resolve=True) or {}
    except Exception as e:
        raise RuntimeError(f"Cannot load config for validation: {e}")

    missing = []
    for path in required:
        cur = full
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                missing.append(path)
                break
            cur = cur[part]
        else:
            if cur is None:
                missing.append(path)

    if missing:
        detail = "\n  ".join(missing)
        raise RuntimeError("Missing required config keys:\n  " + detail)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/config/scopes", response_model=List[str])
def list_config_scopes():
    data = load_config()
    # collect nested scopes
    def _collect(d: Any, prefix="") -> List[str]:
        if not isinstance(d, dict):
            return []
        out = []
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.append(full)
                out.extend(_collect(v, full))
        return out
    return sorted(set(_collect(data)))

class ConfigEntry(BaseModel):
    key: str
    value: Any
    scope: Optional[str] = "global"

class BulkGetRequest(BaseModel):
    keys: List[str]
    scope: Optional[str] = "global"

class BulkSetRequest(BaseModel):
    items: Dict[str, Any]
    scope: Optional[str] = "global"

class RemoveManyRequest(BaseModel):
    keys: List[str]
    scope: Optional[str] = "global"

@app.get("/config/list", response_model=List[ConfigEntry])
def list_config(
    scope: str = Query("global", description="Scope to list, e.g. 'global' or 'service.agents'")
):
    data = load_config()
    section = get_section(data, scope)
    if section is None:
        raise HTTPException(404, f"Scope '{scope}' not found.")
    return [ConfigEntry(key=k, value=v, scope=scope).dict() for k, v in section.items()]

@app.get("/config/get", response_model=ConfigEntry)
def get_config(
    key: str = Query(..., description="Config key to retrieve"),
    scope: str = Query("global", description="Scope to retrieve from")
):
    data = load_config()
    section = get_section(data, scope)
    if section and key in section:
        return ConfigEntry(key=key, value=section[key], scope=scope).dict()
    raise HTTPException(404, f"Key '{key}' not found in scope '{scope}'.")

@app.post("/config/set", response_model=dict)
def set_config(entry: ConfigEntry):
    with CONFIG_LOCK:
        data = load_config(resolve=False)
        section = get_section(data, entry.scope, create_if_missing=True)
        section[entry.key] = entry.value
        save_config(data)
    return {"message": f"Set {entry.key} in {entry.scope}."}

@app.delete("/config/remove", response_model=dict)
def remove_config(
    key: str = Query(..., description="Config key to remove"),
    scope: str = Query("global", description="Scope to remove from")
):
    with CONFIG_LOCK:
        data = load_config(resolve=False)
        section = get_section(data, scope)
        if not section or key not in section:
            raise HTTPException(404, f"Key '{key}' not found in scope '{scope}'.")
        # remove the single key
        del section[key]
        # if that was the last key in this non-global scope, prune the entire branch
        _prune_empty_scope(data, scope)
        save_config(data)
    return {"message": f"Removed {key} from {scope}."}

@app.delete("/config/remove_all", response_model=dict)
def remove_all_config(
    scope: str = Query("global", description="Scope to clear")
):
    with CONFIG_LOCK:
        data = load_config(resolve=False)
        # remove entire branch if non-global, or clear global if requested
        if scope == "global":
            section = get_section(data, "global", create_if_missing=True)
            section.clear()
        else:
            _prune_empty_scope(data, scope)
        save_config(data)
    return {"message": f"Cleared all keys in {scope}."}

@app.post("/config/bulk_get", response_model=dict)
def bulk_get_config(req: BulkGetRequest):
    data = load_config()
    section = get_section(data, req.scope)
    found, missing = {}, []
    if section:
        for k in req.keys:
            if k in section:
                found[k] = section[k]
            else:
                missing.append(k)
    else:
        missing = req.keys.copy()
    return {"values": found, "missing": missing}

@app.post("/config/bulk_set", response_model=dict)
def bulk_set_config(req: BulkSetRequest):
    with CONFIG_LOCK:
        data = load_config(resolve=False)
        section = get_section(data, req.scope, create_if_missing=True)
        for k, v in req.items.items():
            section[k] = v
        save_config(data)
    return {"message": f"Set {len(req.items)} keys in {req.scope}."}

@app.delete("/config/remove_many", response_model=dict)
def remove_many_config(
    keys: Optional[str] = Query(None, description="Comma-delimited keys"),
    scope: str = Query("global", description="Scope to remove from"),
    req: RemoveManyRequest = Body(None)
):
    key_list: List[str] = []
    if keys:
        key_list = [k.strip() for k in keys.split(",") if k.strip()]
    elif req and req.keys:
        key_list = req.keys
        scope = req.scope or scope

    if not key_list:
        raise HTTPException(400, "No keys specified for removal.")

    with CONFIG_LOCK:
        data = load_config(resolve=False)
        section = get_section(data, scope)
        not_found, count = [], 0
        if section:
            for k in key_list:
                if k in section:
                    del section[k]
                    count += 1
                else:
                    not_found.append(k)
            # prune if we removed the last keys in a non-global scope
            _prune_empty_scope(data, scope)
            save_config(data)
        else:
            not_found = key_list.copy()

    return {
        "message": f"Removed {count} keys from {scope}.",
        "not_found": not_found
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(f"{SERVICE_NAME}:app", host="0.0.0.0", port=8010, reload=True)
