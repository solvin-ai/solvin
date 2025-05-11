# modules/line_tracer.py

"""
Line Tracer Module

This module configures a line-by-line tracing function for debugging.
Tracing is controlled via configuration parameters:
  • TRACE_DETAIL_LEVEL: "off" / "low" / "high"
  • TRACE_ALLOWED_PATH: A semicolon‐delimited list of allowed path fragments.
    • If empty, tracing is restricted to files inside the project directory specified by CONFIG["SCRIPT_DIR"].
    • Otherwise, each allowed path is resolved relative to CONFIG["SCRIPT_DIR"] if not absolute.

Only files whose absolute paths match at least one of the allowed paths will be traced.
"""

import sys
import os
import linecache
import logging
from modules.config import config  # our configuration singleton
from modules.logs import logger

# Retrieve configuration as a dictionary.
CONFIG = config.as_dict()

# Set tracing detail level from config (allowed values: "off", "low", "high")
TRACE_DETAIL_LEVEL = CONFIG.get("TRACE_DETAIL_LEVEL", "low").lower()

# Get the script directory from configuration (if provided) or compute it.
script_dir = CONFIG.get("SCRIPT_DIR")

# Retrieve the raw allowed paths from configuration.
raw_allowed = CONFIG.get("TRACE_ALLOWED_PATH", "").strip()

# If raw_allowed is nonempty, split by ';' and resolve each path relative to script_dir if needed.
if raw_allowed:
    parts = [part.strip() for part in raw_allowed.split(";") if part.strip()]
    TRACE_ALLOWED_PATHS = []
    for part in parts:
        if not os.path.isabs(part):
            TRACE_ALLOWED_PATHS.append(os.path.join(script_dir, part))
        else:
            TRACE_ALLOWED_PATHS.append(part)
else:
    # If empty, restrict tracing to files within the project directory.
    TRACE_ALLOWED_PATHS = [script_dir]

# Set up our logger if no handlers are attached.
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    logger.addHandler(handler)

def trace_function(frame, event, arg):
    """
    A configurable trace function that logs line-level details based on TRACE_DETAIL_LEVEL,
    and only if the file being executed is in one of the allowed paths.
    """
    if TRACE_DETAIL_LEVEL == "off":
        return trace_function  # Tracing disabled

    filename = frame.f_code.co_filename

    # Only trace if the filename contains at least one of the allowed path substrings.
    if not any(allowed in filename for allowed in TRACE_ALLOWED_PATHS):
        return trace_function

    if event == "line":
        lineno = frame.f_lineno
        line_str = linecache.getline(filename, lineno).strip()
        if TRACE_DETAIL_LEVEL == "low":
            # In low detail, log only if the line starts with a significant keyword.
            significant_keywords = ("def ", "class ", "if ", "for ", "while ")
            stripped_line = line_str.lstrip()
            if stripped_line and any(stripped_line.startswith(kw) for kw in significant_keywords):
                logger.debug(f"{filename}:{lineno} -> {line_str}")
        elif TRACE_DETAIL_LEVEL == "high":
            # In high detail, log every non-blank line.
            if line_str:
                logger.debug(f"{filename}:{lineno} -> {line_str}")
    return trace_function

def enable_tracing():
    """
    Enable line-by-line tracing according to TRACE_DETAIL_LEVEL (unless set to "off").
    Only files matching the allowed paths will be traced.
    """
    if TRACE_DETAIL_LEVEL != "off":
        sys.settrace(trace_function)

def disable_tracing():
    """
    Disable the tracing function.
    """
    sys.settrace(None)
