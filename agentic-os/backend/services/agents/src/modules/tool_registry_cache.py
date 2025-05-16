# modules/tool_registry_cache.py

import threading
import time

from shared.client_tools import tools_list, tools_info
from shared.logger import logger

class ToolRegistryCache:
    """Singleton-like, thread-safe, hot-reloading tool registry cache."""
    def __init__(self, refresh_interval=300):
        self._lock = threading.RLock()
        self._registry = None
        self._refresh_interval = refresh_interval
        self._bg_thread = None
        self._running = False

    def start_background_refresh(self):
        """Start background refresh thread (idempotent)."""
        with self._lock:
            if self._bg_thread and self._bg_thread.is_alive():
                return
            self._running = True
            # Name the thread for easier debugging
            self._bg_thread = threading.Thread(
                target=self._refresh_loop,
                daemon=True,
                name="ToolRegistryRefresher"
            )
            self._bg_thread.start()

    def stop_background_refresh(self):
        """Request background thread to stop and wait for it."""
        with self._lock:
            self._running = False
        if self._bg_thread:
            self._bg_thread.join(timeout=5)

    def _refresh_loop(self):
        """Background loop that periodically refreshes the registry."""
        logger.info("ToolRegistryCache refresh thread started.")
        while True:
            with self._lock:
                if not self._running:
                    logger.info("ToolRegistryCache stopping refresh thread.")
                    return
            try:
                self.refresh()
            except Exception as e:
                logger.exception("Error refreshing tool registry: %r", e)
            time.sleep(self._refresh_interval)

    def refresh(self):
        """Refresh the tools registry cache immediately."""
        toolnames = [t["tool_name"] for t in tools_list()]
        registry = tools_info(tool_names=toolnames)
        with self._lock:
            self._registry = registry
        count = len(registry) if hasattr(registry, "__len__") else -1
        logger.info("Tool registry cache refreshed: %d entries", count)

    def get_registry(self):
        """
        Retrieve the current registry.
        If not loaded yet, perform an initial refresh.
        """
        with self._lock:
            if self._registry is None:
                self.refresh()
            return self._registry

# Singleton instance
_tool_registry_cache = ToolRegistryCache()

def start_tool_registry_cache_thread(refresh_interval=300):
    """
    Initialize and start the background refresh thread.
    :param refresh_interval: seconds between automatic refreshes (default 300)
    """
    _tool_registry_cache._refresh_interval = refresh_interval
    _tool_registry_cache.start_background_refresh()

def stop_tool_registry_cache_thread():
    """Stop the background refresh thread."""
    _tool_registry_cache.stop_background_refresh()

def get_tools_registry():
    """
    Retrieve the cached tools registry.
    Ensures at least one load has occurred.
    """
    return _tool_registry_cache.get_registry()
