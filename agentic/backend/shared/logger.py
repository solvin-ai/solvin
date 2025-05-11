# shared/logger.py

import logging
import os
import sys
import socket
from pathlib import Path
from contextvars import ContextVar
from datetime import datetime
import shutil
import re
from typing import List

from shared.config import config

# ------------ CONTEXT SUPPORT FOR CORRELATION ID/TRACING ------------
_correlation_id_ctx = ContextVar("correlation_id", default=None)
def set_correlation_id(correlation_id: str):
    _correlation_id_ctx.set(correlation_id)
def get_correlation_id():
    return _correlation_id_ctx.get()

# ------------ CUSTOM TRACE LEVEL SUPPORT ------------
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")

def trace(self, message, *args, **kwargs):
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)
logging.TRACE = TRACE_LEVEL
logging.Logger.trace = trace

# ------------ FORMATTERS ------------
class ColorFormatter(logging.Formatter):
    COLORS = {
        "TRACE": "\033[38;5;208m",   # Orange
        "DEBUG": "\033[32m",         # Green
        "INFO": "\033[34m",          # Blue
        "WARNING": "\033[33m",       # Yellow
        "ERROR": "\033[31m",         # Red
        "CRITICAL": "\033[41m",      # Red bg
    }
    RESET = "\033[0m"
    LIGHT_BLUE = "\033[1;38;19m"

    def __init__(self, fmt=None, datefmt=None):
        if datefmt is None:
            datefmt = "%H:%M:%S"
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record):
        asctime = self.formatTime(record, self.datefmt)
        level_str = f"[{record.levelname}]"
        parent_color = self.COLORS.get(record.levelname, self.RESET)
        # Handle columns if present (dict or list)
        if hasattr(record, 'columns'):
            if isinstance(record.columns, dict):
                keys_order = ["", "Turn", "Tool", "Policy", "Size in/out", "Args", "Extra1", "Extra2"]
                columns = []
                for key in keys_order:
                    if key == "":
                        val = record.columns.get(key, "")
                        columns.append(f"[{val}]".center(15))
                    else:
                        if key in record.columns:
                            col_text = f"{key}: {record.columns[key]}"
                            columns.append(f"[{col_text}]".ljust(30))
                        else:
                            columns.append("".ljust(30))
                message = " | ".join(columns)
            elif isinstance(record.columns, list):
                formatted_columns = [f"{str(col):<30}" for col in record.columns]
                message = " | ".join(formatted_columns)
            else:
                message = str(record.columns)
        else:
            message = record.getMessage()
        # Correlation info (if present)
        correlation = get_correlation_id()
        if correlation:
            message = f"[correlation:{correlation}] {message}"
        # Highlight anything in single quotes
        message = re.sub(r"('.*?')", lambda m: self.LIGHT_BLUE + m.group(0) + parent_color, message)
        # Final
        log_line = f"{asctime} {level_str}: {message}"
        return f"{parent_color}{log_line}{self.RESET}"

def compute_logger_prefix_length():
    dummy_record = logging.LogRecord("dummy", logging.DEBUG, __file__, 0, "", None, None)
    dummy_record.created = 0
    formatter = ColorFormatter(datefmt="%H:%M:%S")
    formatted = formatter.format(dummy_record)
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    no_ansi = ansi_escape.sub('', formatted)
    no_ansi = no_ansi.rstrip()
    return len(no_ansi) + 1

LOG_PREFIX_LENGTH = compute_logger_prefix_length()

# ------------ LOGGER BOOTSTRAP (config-driven, with symlink & 'one logger') ------------

# --- Only use config, never os.environ ---
LOG_DIR = config["LOG_DIR"]
SERVICE_NAME = config["SERVICE_NAME"]

# --- Create log dir ---
log_dir_path = Path(LOG_DIR)
log_dir_path.mkdir(parents=True, exist_ok=True)

# --- Compose JSON log filename ---
now_str = datetime.now().strftime("%Y-%m-%d")
pid = os.getpid()
json_log_filename = f"{SERVICE_NAME}.{now_str}.{pid}.jsonl"
json_log_path = log_dir_path / json_log_filename

# --- Compose terminal log filename (overwritten each run) ---
latest_term_log_path = log_dir_path / f"{SERVICE_NAME}.latest-term.log"

# --- Maintain/update latest symlink (atomic) ---
symlink_name = log_dir_path / f"{SERVICE_NAME}.latest.log"
try:
    tmp_symlink = symlink_name.with_suffix(".tmp")
    try:
        tmp_symlink.unlink()
    except FileNotFoundError:
        pass
    os.symlink(json_log_path.name, tmp_symlink)
    os.replace(tmp_symlink, symlink_name)
except Exception:
    pass

# --- Instantiate the single, system-wide logger ---
_app_logger = logging.getLogger("agentic-os")

LOG_LEVEL = config.get("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL == "TRACE":
    numeric_app_level = TRACE_LEVEL
else:
    numeric_app_level = getattr(logging, LOG_LEVEL, logging.INFO)
_app_logger.setLevel(numeric_app_level)
_app_logger.handlers.clear()
_app_logger.propagate = False

# --- Print log level info on logger startup ---
#print(f"[logger.py] LOG_LEVEL='{LOG_LEVEL}' numeric={numeric_app_level} for SERVICE_NAME='{SERVICE_NAME}'", file=sys.stderr)

# --- Console (stream) handler, with Rich logs if possible ---
try:
    from rich.logging import RichHandler
    stream_handler = RichHandler(rich_tracebacks=True, show_time=True, show_level=True, show_path=True)
    _app_logger.addHandler(stream_handler)
except ImportError:
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(ColorFormatter())
    _app_logger.addHandler(stream_handler)

# --- Terminal file handler: dump latest terminal (overwritten) ---
class LatestTermFileHandler(logging.FileHandler):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, mode='w', encoding='utf-8', **kwargs)
    def emit(self, record):
        msg = self.format(record)
        self.stream.write(msg + "\n")
        self.flush()

term_file_handler = LatestTermFileHandler(latest_term_log_path)
# Use the same formatter as terminal/console.
term_file_handler.setFormatter(getattr(stream_handler, 'formatter', None))
_app_logger.addHandler(term_file_handler)

# --- File handler (JSON only for main backend log) ---
try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:
    raise ImportError("python-json-logger must be installed for JSON logging.")

json_log_handler = logging.FileHandler(json_log_path, encoding="utf-8")
json_formatter = JsonFormatter(
    "%(asctime)s %(levelname)s %(name)s %(filename)s %(module)s %(lineno)d %(message)s"
)
json_log_handler.setFormatter(json_formatter)
_app_logger.addHandler(json_log_handler)

# --- Expose logger singleton ---
logger = _app_logger

# -------------- GLOBAL RICH CONSOLE (optional) --------------
try:
    from rich.console import Console
    console = Console()
except ImportError:
    console = None

# ------------ CONTEXT API UTILS (export for users) ------------
set_correlation_id = set_correlation_id
get_correlation_id = get_correlation_id

# ------------ UTILITIES: header, line, log_columns, log_table ------------

def header(self, text: str, level=logging.INFO):
    terminal_width = shutil.get_terminal_size(fallback=(80, 20)).columns
    available_width = terminal_width - LOG_PREFIX_LENGTH
    if available_width < 0:
        available_width = terminal_width
    content = f"[ {text} ]"
    available = available_width - len(content) - 2
    if available < 0: available = 0
    left_dashes = available // 2
    right_dashes = available - left_dashes
    header_line = ("═" * left_dashes) + " " + content + " " + ("═" * right_dashes)
    self.log(level, header_line)
logger.header = header.__get__(logger, type(logger))

def line(self, level=logging.INFO, message=None, style=1):
    terminal_width = shutil.get_terminal_size(fallback=(80, 20)).columns
    available_width = terminal_width - LOG_PREFIX_LENGTH
    if available_width < 0:
        available_width = terminal_width
    if message is None:
        separator_char = "═" if style == 2 else '-'
        message = separator_char * available_width
    self.log(int(level), message)
logger.line = line.__get__(logger, type(logger))

def log_columns(self, columns: List, level=logging.INFO):
    colstr = " | ".join(str(c) for c in columns)
    self.log(level, colstr, extra={"columns": columns})
logger.log_columns = log_columns.__get__(logger, type(logger))

def rich_table(title, columns, rows):
    if console:
        from rich.table import Table
        t = Table(title=title)
        for c in columns:
            t.add_column(str(c))
        for r in rows:
            t.add_row(*[str(item) for item in r])
        return t
    else:
        header = " | ".join(columns)
        lines = [" | ".join(map(str, row)) for row in rows]
        return "\n".join([header] + lines)

def log_table(title, columns, rows):
    if console:
        console.print(rich_table(title, columns, rows))
    else:
        logger.info(rich_table(title, columns, rows))
logger.rich_table = rich_table
logger.log_table = log_table

def get_log_path():
    return json_log_path

# ------------- EXAMPLE USAGE -------------
if __name__ == "__main__":
    set_correlation_id("REQ-26571")
    logger.header("SERVICE STARTUP")
    logger.info("Startup complete.")
    logger.trace("This is a TRACE event (single-letter T)")
    logger.warning("Warning test.")
    try:
        1/0
    except Exception:
        logger.exception("Division error!")
    logger.line()
    logger.log_columns(["col1", "col2", "col3"])
    logger.header("Tabular Example")
    logger.log_table("Table Example", ["A", "B"], [["row1valA", "row1valB"], ["row2valA", "row2valB"]])
    set_correlation_id(None)
    logger.info("Goodbye. Service stopped.")
