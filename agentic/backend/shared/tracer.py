# shared/tracer.py

"""
Line Tracer Module

This module configures a line-by-line tracing function for debugging.
Reads config from `modules.config.config` singleton:
  • TRACE_DETAIL_LEVEL: "off" / "low" / "high"
  • TRACE_ALLOWED_PATH: Semicolon-delimited list of allowed path fragments.
    - If empty, only files within SCRIPT_DIR are traced.
    - Paths are resolved relative to SCRIPT_DIR if not absolute.

Uses the logger from shared.logger.
"""

import sys
import os
import linecache

from shared.config import config

# Use the configured logger from your project
try:
    from shared.logger import logger  # Ideally, your rich/json global logger is here!
except ImportError:
    import logging
    logger = logging.getLogger("tracer")
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        logger.setLevel(logging.DEBUG)
        logger.addHandler(h)

def _get_config(key, default=None):
    # Helper in case config is a proxy object
    if hasattr(config, "as_dict"):
        return config.as_dict().get(key, default)
    return getattr(config, key, default)

SCRIPT_DIR = _get_config("SCRIPT_DIR", os.getcwd())
TRACE_DETAIL_LEVEL = (_get_config("TRACE_DETAIL_LEVEL", "off") or "off").lower()
RAW_ALLOWED_PATHS = (_get_config("TRACE_ALLOWED_PATH", "") or "").strip()

if RAW_ALLOWED_PATHS:
    # Accept ; or : as delimiters
    parts = [part.strip() for part in RAW_ALLOWED_PATHS.replace(":", ";").split(";") if part.strip()]
    TRACE_ALLOWED_PATHS = [
        os.path.abspath(os.path.join(SCRIPT_DIR, p)) if not os.path.isabs(p) else p
        for p in parts
    ]
else:
    TRACE_ALLOWED_PATHS = [os.path.abspath(str(SCRIPT_DIR))]

def _allowed(filename):
    abspath = os.path.abspath(filename)
    return any(
        abspath.startswith(allowed)
        for allowed in TRACE_ALLOWED_PATHS
    )

def trace_function(frame, event, arg):
    if TRACE_DETAIL_LEVEL == "off":
        return trace_function
    filename = frame.f_code.co_filename
    if not _allowed(filename):
        return trace_function
    if event == "line":
        lineno = frame.f_lineno
        line_str = linecache.getline(filename, lineno).rstrip()
        if not line_str.strip():
            return trace_function
        if TRACE_DETAIL_LEVEL == "low":
            keywords = ("def ", "class ", "if ", "for ", "while ")
            if line_str.lstrip().startswith(keywords):
                logger.debug(f"[TRACE] {filename}:{lineno} -> {line_str}")
        elif TRACE_DETAIL_LEVEL == "high":
            logger.debug(f"[TRACE] {filename}:{lineno} -> {line_str}")
    return trace_function

def enable_tracing():
    if TRACE_DETAIL_LEVEL != "off":
        sys.settrace(trace_function)

def disable_tracing():
    sys.settrace(None)

if __name__ == "__main__":
    logger.info("Enabling line-by-line tracing for demo (set config values to see effect)...")
    enable_tracing()
    # A small demo traceable section
    def demo():
        x = 1
        for i in range(3):
            x += i
        if x > 2:
            x *= 2
        return x
    demo()
    disable_tracing()
    logger.info("Demo finished.")
