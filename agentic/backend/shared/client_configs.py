# shared/client_configs.py

"""
Config client for microservice configs—API proxy only.

All calls go straight to the config service URL defined by env var SERVICE_URL_CONFIGS
(or default localhost:8010). No local config files are read. No process‐level caching
except for API lookups within this process. Values retain their native types:
str, int, bool, list, dict.
"""

import os
import requests
from typing import Optional, Dict, List, Any

# Config service base URL: from env or default
SERVICE_URL_CONFIGS = os.environ.get("SERVICE_URL_CONFIGS", "http://localhost:8010")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "UNKNOWN_SERVICE")

def _default_scope() -> str:
    return "global"

def _resolve_scope(scope: Optional[str]) -> str:
    return _default_scope() if scope is None else str(scope)

# Minimal per‐process (runtime only) cache
class ClientCache:
    def __init__(self):
        self._store: Dict[(str,str), Any] = {}

    def get(self, key: str, scope: str) -> Any:
        return self._store.get((scope, key))

    def set(self, key: str, scope: str, value: Any):
        self._store[(scope, key)] = value

    def remove(self, key: str, scope: str):
        self._store.pop((scope, key), None)

    def remove_many(self, keys: List[str], scope: str):
        for k in keys:
            self.remove(k, scope)

    def clear_scope(self, scope: str):
        for (s, k) in list(self._store.keys()):
            if s == scope:
                del self._store[(s, k)]

    def clear(self):
        self._store.clear()

_client_cache = ClientCache()

def list_scopes() -> List[str]:
    """
    Return a sorted list of all scopes, e.g. ["global","service.agents",...]
    """
    try:
        resp = requests.get(f"{SERVICE_URL_CONFIGS}/config/scopes")
        resp.raise_for_status()
        return sorted(resp.json())
    except Exception as e:
        raise RuntimeError(f"Error listing config scopes: {e}")

def list_config(scope: Optional[str] = None, nocache: bool = False) -> Dict[str, Any]:
    """
    List all key→value pairs in the given scope.
    Returns a dict of native‐typed values.
    If the scope does not exist (404), returns {}.
    """
    the_scope = _resolve_scope(scope)
    try:
        resp = requests.get(
            f"{SERVICE_URL_CONFIGS}/config/list",
            params={"scope": the_scope},
        )
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        entries = resp.json()  # expect List[{"key":..., "value":..., "scope":...}]
        result: Dict[str, Any] = {}
        for e in entries:
            key = e["key"]
            val = e["value"]
            result[key] = val
            if not nocache:
                _client_cache.set(key, the_scope, val)
        return result
    except Exception as e:
        raise RuntimeError(f"Error listing config for scope '{the_scope}': {e}")

def get_config(
    key: str,
    default: Any = None,
    scope: Optional[str] = None,
    nocache: bool = False
) -> Any:
    """
    Retrieve a single config key from a scope.
    Returns native‐typed value or `default` if provided.
    Raises if not found and no default.
    """
    the_scope = _resolve_scope(scope)
    if not nocache:
        cached = _client_cache.get(key, the_scope)
        if cached is not None:
            return cached

    try:
        resp = requests.get(
            f"{SERVICE_URL_CONFIGS}/config/get",
            params={"key": key, "scope": the_scope},
        )
        if resp.status_code == 200:
            val = resp.json().get("value")
            if not nocache:
                _client_cache.set(key, the_scope, val)
            return val
        elif resp.status_code == 404 and default is not None:
            return default
        else:
            resp.raise_for_status()
    except Exception as e:
        if default is not None:
            return default
        raise RuntimeError(f"Error getting config '{key}' from scope '{the_scope}': {e}")

def set_config(key: str, value: Any, scope: Optional[str] = None) -> None:
    """
    Set or overwrite a single key→value in the given scope.
    Value can be bool, int, list, dict, etc.
    """
    the_scope = _resolve_scope(scope)
    payload = {"key": key, "value": value, "scope": the_scope}
    try:
        resp = requests.post(f"{SERVICE_URL_CONFIGS}/config/set", json=payload)
        resp.raise_for_status()
        _client_cache.remove(key, the_scope)
    except Exception as e:
        raise RuntimeError(f"Error setting config '{key}' in '{the_scope}': {e}")

def remove_config(key: str, scope: Optional[str] = None) -> None:
    """
    Remove a single config entry. The server will also prune
    the entire scope block if it becomes empty.
    """
    the_scope = _resolve_scope(scope)
    try:
        resp = requests.delete(
            f"{SERVICE_URL_CONFIGS}/config/remove",
            params={"key": key, "scope": the_scope},
        )
        resp.raise_for_status()
        _client_cache.remove(key, the_scope)
    except Exception as e:
        _client_cache.remove(key, the_scope)
        raise RuntimeError(f"Error removing config '{key}' in '{the_scope}': {e}")

def remove_all_config(scope: Optional[str] = None) -> None:
    """
    Remove all keys in the given scope (or clear global).
    """
    the_scope = _resolve_scope(scope)
    try:
        resp = requests.delete(
            f"{SERVICE_URL_CONFIGS}/config/remove_all",
            params={"scope": the_scope},
        )
        resp.raise_for_status()
        _client_cache.clear_scope(the_scope)
    except Exception as e:
        raise RuntimeError(f"Error removing all config in '{the_scope}': {e}")

def remove_many_config(keys: List[str], scope: Optional[str] = None) -> None:
    """
    Remove many keys at once in the given scope.
    """
    the_scope = _resolve_scope(scope)
    payload = {"keys": keys, "scope": the_scope}
    try:
        resp = requests.delete(f"{SERVICE_URL_CONFIGS}/config/remove_many", json=payload)
        resp.raise_for_status()
        _client_cache.remove_many(keys, the_scope)
    except Exception as e:
        raise RuntimeError(f"Error removing many config keys in '{the_scope}': {e}")

def bulk_get_config(
    keys: List[str],
    scope: Optional[str] = None,
    nocache: bool = False
) -> Dict[str, Any]:
    """
    Retrieve multiple keys at once; returns a dict of key→value.
    Missing keys are simply absent from the dict.
    """
    the_scope = _resolve_scope(scope)
    payload = {"keys": keys, "scope": the_scope}
    try:
        resp = requests.post(f"{SERVICE_URL_CONFIGS}/config/bulk_get", json=payload)
        resp.raise_for_status()
        data = resp.json().get("values", {})
        if not nocache:
            for k, v in data.items():
                _client_cache.set(k, the_scope, v)
        return data
    except Exception as e:
        raise RuntimeError(f"Error in bulk_get_config: {e}")

def bulk_set_config(items: Dict[str, Any], scope: Optional[str] = None) -> None:
    """
    Set multiple key→value pairs at once in the given scope.
    """
    the_scope = _resolve_scope(scope)
    payload = {"items": items, "scope": the_scope}
    try:
        resp = requests.post(f"{SERVICE_URL_CONFIGS}/config/bulk_set", json=payload)
        resp.raise_for_status()
        _client_cache.remove_many(list(items.keys()), the_scope)
    except Exception as e:
        raise RuntimeError(f"Error in bulk_set_config: {e}")

def health() -> Dict[str, Any]:
    """
    Check health of the config service.
    """
    try:
        resp = requests.get(f"{SERVICE_URL_CONFIGS}/health")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Error contacting config service health endpoint: {e}")

class ConfigDict:
    """
    dict‐like access to global scope:
      config["KEY"]               # get
      config["KEY"] = value       # set
      "KEY" in config             # exists?
      config.get("KEY", default)  # with default
      config.keys(), config.items()
    """
    def __getitem__(self, key: str) -> Any:
        return get_config(key)

    def __setitem__(self, key: str, value: Any):
        set_config(key, value)
        _client_cache.set(key, _default_scope(), value)

    def get(self, key: str, default: Any = None, scope: Optional[str] = None, nocache: bool = False) -> Any:
        return get_config(key, default=default, scope=scope, nocache=nocache)

    def __contains__(self, key: str) -> bool:
        try:
            get_config(key)
            return True
        except:
            return False

    def keys(self, scope: Optional[str] = None) -> List[str]:
        return list(list_config(scope).keys())

    def items(self, scope: Optional[str] = None) -> List[tuple]:
        return list(list_config(scope).items())

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(self.keys())

    def clear_cache(self):
        _client_cache.clear()

config = ConfigDict()

if __name__ == "__main__":
    print("Config service URL:", SERVICE_URL_CONFIGS)
    print("Global config:", list_config())
    print("Health:", health())
