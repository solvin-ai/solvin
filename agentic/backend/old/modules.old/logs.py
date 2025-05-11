# modules/logs.py

"""
Sets up logging for the application with both stream (colored logs) and OpenAI logging.

Enhancements in this version:
  • Adds a custom TRACE level and a trace() method on Logger.
  • Uses a unified format that includes a timestamp (HH:MM:SS), a single-letter log level,
    the script filename (without the .py extension, padded to 31 characters), and a custom,
    fixed–width, multi-column message.
  • Supports an optional 'columns' attribute in log records for multi-column alignment.
  • Provides helper methods to print separator lines and headers.
  • logger.line() now supports a call signature where the log level is the first argument,
    followed by the message (if any) and an optional style parameter.
  • The helper methods adjust to the terminal’s current width (accounting for the log prefix).
  • Exposes LOG_PREFIX_LENGTH for other modules to use.
"""

import logging
import os
import shutil
import re
from modules.config import config  # Using the config singleton instead of read_config

# Define custom TRACE level (numeric value lower than DEBUG)
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")
logging.TRACE = TRACE_LEVEL

TERMINAL_WIDTH = shutil.get_terminal_size(fallback=(80, 20)).columns

def trace(self, message, *args, **kwargs):
    """
    Log 'message' with severity 'TRACE' on the logger.
    """
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)

# Attach the new trace() method to all Logger instances.
logging.Logger.trace = trace

class ColorFormatter(logging.Formatter):
    """
    Custom formatter that outputs the log record in the following format:

       HH:MM:SS [L] [filename                 ]: <columns or message>

    where [L] is a single letter representing the log level:
      • [I] for INFO,
      • [D] for DEBUG,
      • [W] for WARNING,
      • [E] for ERROR,
      • [T] for TRACE,
      • any other level falls back to its first character.

    The filename is displayed without the ".py" extension and is allocated
    a fixed field of 31 characters to ensure proper alignment.

    When a log record has an extra attribute 'columns', it will be formatted as fixed–width columns.
    If 'columns' is a dictionary, a predefined ordering is used to display each field as "[Key: value]".
    If 'columns' is a list, then each element is padded to a fixed width.
    ANSI color codes are applied based on the log level.

    Additionally, any term wrapped in single quotes (e.g., 'this text')
    will be displayed in a lighter blue.
    """
    # ANSI escape sequences for colors.
    COLORS = {
        "TRACE": "\033[38;5;208m",   # Orange for trace
        "DEBUG": "\033[32m",         # Green for debug
        "INFO": "\033[34m",          # Blue for info
        "WARNING": "\033[33m",       # Yellow for warning
        "ERROR": "\033[31m",         # Red for error
        "CRITICAL": "\033[41m",      # Red background for critical
    }
    RESET = "\033[0m"  # Reset color
    # Lighter blue color for terms wrapped in single quotes.
    LIGHT_BLUE = "\033[1;38;19m"

    def __init__(self, fmt=None, datefmt=None):
        # Default timestamp format is HH:MM:SS.
        if datefmt is None:
            datefmt = "%H:%M:%S"
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record):
        # Format the timestamp using the formatter’s datefmt.
        asctime = self.formatTime(record, self.datefmt)
        # Map full level names to a single letter.
        level_letters = {
            "TRACE": "T",
            "DEBUG": "D",
            "INFO": "I",
            "WARNING": "W",
            "ERROR": "E",
            "CRITICAL": "C"
        }
        # Use the mapped letter or fall back to the first character.
        level_letter = level_letters.get(record.levelname, record.levelname[0])
        level_str = f"[{level_letter}]"
        # Remove the .py extension from the filename (if present),
        # then pad the filename to a total width of 31 characters.
        file_name = record.filename[:-3] if record.filename.endswith(".py") else record.filename
        file_str = f"[{file_name:<31}]"
        # Get the appropriate ANSI color based on the log level.
        parent_color = self.COLORS.get(record.levelname, self.RESET)
        # Build the message, using the extra 'columns' attribute if present.
        if hasattr(record, 'columns'):
            if isinstance(record.columns, dict):
                # Use a predefined ordering for columns.
                keys_order = ["", "Turn", "Tool", "Policy", "Size in/out", "Args", "Extra1", "Extra2"]
                columns = []
                for key in keys_order:
                    if key == "":
                        # For the first (possibly empty) column, center within a 15-character field.
                        val = record.columns.get(key, "")
                        columns.append(f"[{val}]".center(15))
                    else:
                        if key in record.columns:
                            col_text = f"{key}: {record.columns[key]}"
                            # Pad each column to 30 characters.
                            columns.append(f"[{col_text}]".ljust(30))
                        else:
                            # If key is omitted, use an empty fixed-width field.
                            columns.append("".ljust(30))
                message = " | ".join(columns)
            elif isinstance(record.columns, list):
                # If columns is a list, pad each element to 30 characters.
                formatted_columns = [f"{str(col):<30}" for col in record.columns]
                message = " | ".join(formatted_columns)
            else:
                # Fallback if columns is provided in an unexpected format.
                message = str(record.columns)
        else:
            message = record.getMessage()
        # Color any term wrapped in single quotes in lighter blue.
        message = re.sub(r"('.*?')", lambda m: self.LIGHT_BLUE + m.group(0) + parent_color, message)
        # Assemble the complete log line.
        log_line = f"{asctime} {level_str} {file_str}: {message}"
        return f"{parent_color}{log_line}{self.RESET}"

def setup_logging():
    """
    Reads configuration for the main (app) and OpenAI logger settings.
    """
    app_log_level = config.get("LOG_LEVEL", "INFO").upper()
    numeric_app_level = getattr(logging, app_log_level, logging.INFO)

    # Configure the main application logger.
    app_logger = logging.getLogger("app")
    app_logger.setLevel(numeric_app_level)

    if not app_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(ColorFormatter())
        app_logger.addHandler(stream_handler)
        # Prevent messages from propagating to the root logger.
        app_logger.propagate = False

    # Configure the OpenAI logger using the OPENAI_LOG environment variable.
    openai_log_level = os.environ.get("OPENAI_LOG", "WARNING").upper()
    numeric_openai_level = getattr(logging, openai_log_level, logging.WARNING)
    openai_logger = logging.getLogger("openai")
    openai_logger.setLevel(numeric_openai_level)

    return app_logger

# Set up and export the app logger.
logger = setup_logging()

def compute_logger_prefix_length():
    """
    Computes and returns the length of the log prefix (e.g., "HH:MM:SS [L] [filename                 ]: ")
    as printed by our ColorFormatter when using an empty message.
    ANSI escape sequences are stripped before measuring.
    """
    dummy_record = logging.LogRecord("dummy", logging.DEBUG, __file__, 0, "", None, None)
    # Set a fixed timestamp to ensure a consistent asctime (e.g. "00:00:00")
    dummy_record.created = 0
    formatter = ColorFormatter(datefmt="%H:%M:%S")
    formatted = formatter.format(dummy_record)
    # Remove ANSI escape sequences.
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    no_ansi = ansi_escape.sub('', formatted)
    # Remove any trailing whitespace.
    no_ansi = no_ansi.rstrip()
    return len(no_ansi) + 1

# Expose the computed logger prefix length to other modules.
LOG_PREFIX_LENGTH = compute_logger_prefix_length()

def line(self, level=logging.INFO, message=None, style=1):
    """
    Logs a custom message at the given level, or if no message is provided,
    prints a separator line (spanning the terminal width).

    The 'style' parameter controls the separator character:
      - style=1 uses '-' characters;
      - style=2 uses '═' characters.
    """
    terminal_width = shutil.get_terminal_size(fallback=(80, 20)).columns
    available_width = terminal_width - LOG_PREFIX_LENGTH
    if available_width < 0:
        available_width = terminal_width
    # If no message is given, generate a separator line.
    if message is None:
        separator_char = "═" if style == 2 else '-'
        message = separator_char * available_width
    # Ensure level is an integer.
    self.log(int(level), message)

# Bind line() to our logger instance.
logger.line = line.__get__(logger, type(logger))

def header(self, text, level=logging.INFO):
    """
    Print a decorated header that (with the log prefix) spans the full terminal width.
    Adjusts for the length of the log prefix.
    """
    terminal_width = shutil.get_terminal_size(fallback=(80, 20)).columns
    available_width = terminal_width - LOG_PREFIX_LENGTH
    if available_width < 0:
        available_width = terminal_width
    content = f"[ {text} ]"
    # Calculate remaining space for the header decoration.
    available = available_width - len(content) - 2  # 2 extra spaces for padding around content.
    if available < 0:
        available = 0
    left_dashes = available // 2
    right_dashes = available - left_dashes
    header_line = ("═" * left_dashes) + " " + content + " " + ("═" * right_dashes)
    self.log(level, header_line)

# Bind header() to our logger.
logger.header = header.__get__(logger, type(logger))
