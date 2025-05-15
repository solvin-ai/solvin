# shared/config.py

"""
Unified config access for all services and tests.

- SERVICE_NAME should be set at top of your service file before you
  ask for any other config key:
      import shared.config as config
      config["SERVICE_NAME"] = "my_service"
- If SERVICE_NAME is NOT set in config, config will check os.environ.
- If neither is set, config acts in 'global' scope (intended for CLI).
- SERVICE_SCOPE is auto-constructed from SERVICE_NAME (underscores → dots).
- Reads (config["key"], config.get("key")) default to SERVICE_SCOPE,
  with fallback to "global".
- Writes/remove_config: In-memory only (not persisted).
- If a key is not found in config service/global, falls back to os.environ.
"""

import os
from typing import Any, MutableMapping, Optional, Iterator, Tuple
from shared.client_configs import get_config as _remote_get_config

# debug flag
DEBUG_CONFIG = os.environ.get("SOLVIN_CONFIG_DEBUG", "0") == "1"
def debug_print(msg: str):
    if DEBUG_CONFIG:
        print(f"[CONFIG DEBUG] {msg!r}")

# sentinel to detect "no default passed"
_NO_DEFAULT = object()

class LazyConfigDict(MutableMapping):
    """
    Dict-like config with service-automatic scoping and global fallback.
    """

    def __init__(self):
        # in-memory overrides & cache: keys are (config_key, scope_name)
        self._local: dict[Tuple[str, str], Any] = {}

    def _get_service_name(self) -> Optional[str]:
        # 1) in-memory override
        sn = self._local.get(("SERVICE_NAME", "global"))
        if sn:
            return sn
        # 2) environment
        sn = os.environ.get("SERVICE_NAME")
        if sn:
            return sn
        # 3) none set
        return None

    def _get_service_scope(self) -> str:
        """
        Turn SERVICE_NAME into scope string, or return "global".
        Normalizes "_" → "." so that e.g. "aaa_bbb" → "aaa.bbb".
        """
        sn = self._get_service_name()
        if not sn:
            return "global"
        return sn.replace("_", ".")

    def _cache_key(self, key: str, scope: Optional[str] = None) -> Tuple[str, str]:
        scope = scope or self._get_service_scope()
        return (key, scope)

    def __getitem__(self, key: str) -> Any:
        # SERVICE_NAME never raises
        if key == "SERVICE_NAME":
            return self._get_service_name()
        # other keys: missing → KeyError
        return self.get(key, default=_NO_DEFAULT)

    def get(
        self,
        key: str,
        default: Any = _NO_DEFAULT,
        scope: Optional[str] = None
    ) -> Any:
        # special-case SERVICE_NAME
        if key == "SERVICE_NAME":
            sn = self._get_service_name()
            if sn is not None:
                return sn
            # either return explicit default, or None if none given
            if default is not _NO_DEFAULT:
                return default
            return None

        main_scope = scope or self._get_service_scope()
        ckey = self._cache_key(key, main_scope)

        # 1) in-memory
        if ckey in self._local:
            return self._local[ckey]

        # 2) environment fallback
        envv = os.environ.get(key)
        if envv is not None:
            return envv

        # 3) remote config service: try main scope, then global
        for try_scope in (main_scope, "global"):
            try:
                val = _remote_get_config(key, default=None, scope=try_scope)
            except Exception:
                continue
            if val is not None:
                self._local[(key, try_scope)] = val
                return val
            else:
                debug_print(f"{key} not in remote[{try_scope}]")

        # 4) explicit default?
        if default is not _NO_DEFAULT:
            debug_print(f"{key} missing → using default={default!r}")
            return default

        # nowhere found → KeyError
        debug_print(f"{key} missing in scopes/env, no default → KeyError")
        raise KeyError(
            f"Config key '{key}' not found in scope '{main_scope}', "
            "global, or environment (and no default)"
        )

    def set(self, key: str, value: Any, scope: Optional[str] = None) -> None:
        """
        In-memory-only override. Behaves like config[key] = value,
        but can explicitly specify a scope if desired.
        """
        if key == "SERVICE_NAME":
            scope = "global"
        else:
            scope = scope or self._get_service_scope()
        self._local[(key, scope)] = value

    def __setitem__(self, key: str, value: Any) -> None:
        scope = "global" if key == "SERVICE_NAME" else self._get_service_scope()
        self._local[(key, scope)] = value

    def __delitem__(self, key: str) -> None:
        ckey = self._cache_key(key)
        if ckey in self._local:
            del self._local[ckey]
        else:
            raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if key == "SERVICE_NAME":
            return self._get_service_name() is not None
        if not isinstance(key, str):
            return False
        ckey = self._cache_key(key)
        return ckey in self._local

    def __iter__(self) -> Iterator[str]:
        return (k for (k, _) in self._local)

    def __len__(self) -> int:
        return len(self._local)

    def clear_cache(self) -> None:
        """Clear in-memory config cache."""
        self._local.clear()


config = LazyConfigDict()


def remove_config(key: str, scope: Optional[str] = None) -> bool:
    """
    Remove a key from the in-memory cache only.
    Returns True if it was present and removed.
    """
    ckey = config._cache_key(key, scope)
    if ckey in config._local:
        del config._local[ckey]
        return True
    return False
