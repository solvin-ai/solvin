# modules/cli_errorhandler.py

import os
import sys
import typer
import traceback
from modules.cli_core import banner

# Try to import common HTTP/network exception types
try:
    from requests.exceptions import RequestException as _ReqExc, ConnectionError as _ReqConnErr
except ImportError:
    _ReqExc = _ReqConnErr = None

try:
    import httpx
    _HttpxErr = httpx.HTTPError
except ImportError:
    _HttpxErr = None

try:
    import urllib3.exceptions as _u3exc
    _U3Err = _u3exc.HTTPError
except ImportError:
    _U3Err = None

from urllib.error import URLError as _URLErr
import socket

# This flag will be flipped by the --debug CLI option
DEBUG = False

def _in_debug_mode() -> bool:
    """
    Return True if either:
      - the --debug flag was passed (which sets our DEBUG flag), or
      - SOLVIN_DEBUG env var is set to a non‐empty, non‐0, non‐false value.
    """
    if DEBUG:
        return True
    v = os.getenv("SOLVIN_DEBUG", "")
    return v.lower() not in ("", "0", "false", "no")

def bannering_handle_exception(exc_type, exc_value, exc_traceback):
    """
    Global exception hook that prints a banner (if in a TTY)
    followed by a user‐friendly error message for:
      1) Missing SERVICE_URL_AGENTS config
      2) Other missing‐config KeyError
      3) Network/connection errors
      4) Fallback for anything else (with optional full traceback)
    """
    # 0) Print banner if interactive
    if sys.stdout.isatty():
        banner()

    # 1) Missing SERVICE_URL_AGENTS
    if exc_type is KeyError and "SERVICE_URL_AGENTS" in str(exc_value):
        typer.echo("❌ Configuration error: SERVICE_URL_AGENTS is not set.")
        typer.echo("   Please check your config files or environment variables.")
        sys.exit(1)

    # 2) Generic missing‐config KeyError
    if exc_type is KeyError and "Config key" in str(exc_value):
        typer.echo(f"❌ {exc_value}")
        sys.exit(1)

    # 3) Backend‐unavailable / network errors
    network_errors = []
    if _ReqConnErr:
        network_errors.append(_ReqConnErr)
    if _ReqExc:
        network_errors.append(_ReqExc)
    if _HttpxErr:
        network_errors.append(_HttpxErr)
    if _U3Err:
        network_errors.append(_U3Err)
    network_errors.extend([_URLErr, ConnectionRefusedError, socket.timeout])

    if isinstance(exc_value, tuple(network_errors)):
        typer.echo("❌ Backend service is not reachable.")
        typer.echo("   Please verify the service is up and network is OK.")
        sys.exit(1)

    # 4) Fallback for anything else
    typer.echo("❌ An unexpected error has occurred.")
    if _in_debug_mode():
        # print full Python traceback
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
    sys.exit(1)
