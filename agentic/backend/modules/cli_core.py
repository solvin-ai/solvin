# modules/cli_core.py

from __future__ import annotations

import os
import sys
import select
import time
import logging
from typing import Optional

import typer
from typer import Context, Option
import click

# ---------------------------------------------------------------------------#
# Logging (uses project logger if available, otherwise stdlib fallback)
# ---------------------------------------------------------------------------#
try:
    from modules.logs import logger
except ImportError:
    logger = logging.getLogger("cli_core")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

# ---------------------------------------------------------------------------#
# Platform detection (Windows vs POSIX) and raw-key helpers
# ---------------------------------------------------------------------------#
try:
    import msvcrt  # type: ignore
    WINDOWS = True
except ImportError:
    WINDOWS = False
    import termios
    import tty

# ---------------------------------------------------------------------------#
# Globals
# ---------------------------------------------------------------------------#
_skip_prompts   = False       # set to True when user presses “s” to skip pauses
_no_banner      = False       # set to True to suppress banner()
_http_timeout: Optional[float] = None  # global HTTP timeout in seconds

def set_no_banner(flag: bool) -> None:
    """
    Globally suppress future banner() calls when flag is True.
    """
    global _no_banner
    _no_banner = bool(flag)

def set_http_timeout(seconds: float) -> None:
    """
    Set a global timeout (in seconds) for all downstream HTTP requests.
    """
    global _http_timeout
    _http_timeout = seconds

def get_http_timeout() -> Optional[float]:
    """
    Returns the global HTTP timeout (or None if unset, meaning use requests' default).
    """
    return _http_timeout

# ---------------------------------------------------------------------------#
# Banner
# ---------------------------------------------------------------------------#
def banner() -> None:
    """
    Print the ASCII banner only when stdout is an interactive TTY
    and banner suppression is not requested.
    """
    if _no_banner or not sys.stdout.isatty():
        return

    ascii_banner = r"""
 ____        _       _
/ ___|  ___ | |_   _(_)_ __
\___ \ / _ \| \ \ / / | '_ \
 ___) | (_) | |\ V /| | | | |
|____/ \___/|_| \_/ |_|_| |_|

"""
    sys.stdout.write(ascii_banner)
    sys.stdout.flush()

# ---------------------------------------------------------------------------#
# Low‐level single‐character input helpers
# ---------------------------------------------------------------------------#
def _getch() -> str:
    if WINDOWS:
        return msvcrt.getch().decode("utf-8", errors="ignore")
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        logger.warning("stdin is not a TTY; cannot read single key.")
        return ""
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch

def _getch_nonblocking() -> Optional[str]:
    if WINDOWS:
        if msvcrt.kbhit():
            return msvcrt.getch().decode("utf-8", errors="ignore")
        return None
    dr, _, _ = select.select([sys.stdin], [], [], 0)
    if dr and sys.stdin in dr:
        try:
            return sys.stdin.read(1)
        except Exception as exc:
            logger.debug("Non-blocking read error: %s", exc)
    return None

# ---------------------------------------------------------------------------#
# Interruptible countdown (used by interactive_pause)
# ---------------------------------------------------------------------------#
def _interruptible_countdown(total_seconds: float) -> None:
    global _skip_prompts

    remaining = float(total_seconds)
    paused = False
    tick = 0.1
    fd = None
    old_settings = None
    raw_mode_set = False

    if not WINDOWS and sys.stdin.isatty():
        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            raw_mode_set = True
        except Exception as exc:
            logger.debug("Unable to set cbreak mode: %s", exc)

    try:
        start_ts = time.monotonic()
        pause_started: Optional[float] = None
        longest_line = 0

        while remaining > 0:
            now = time.monotonic()
            if paused:
                if pause_started is None:
                    pause_started = now
                msg = "Countdown paused (p=resume, q=quit, s=skip all, other=skip now)…"
            else:
                if pause_started is not None:
                    start_ts += now - pause_started
                    pause_started = None
                elapsed = now - start_ts
                remaining = total_seconds - elapsed
                if remaining <= 0:
                    break
                msg = (
                    f"Resuming in {int(remaining)+1} s "
                    "(p=pause, q=quit, s=skip all, other=skip now)"
                )

            sys.stdout.write(f"{msg:<{longest_line}}\r")
            sys.stdout.flush()
            longest_line = max(longest_line, len(msg))

            key = _getch_nonblocking()
            if key:
                sys.stdout.write(" " * longest_line + "\r")
                sys.stdout.flush()
                kl = key.lower()
                if kl == "q":
                    logger.info("User pressed 'q' during countdown – exiting.")
                    sys.exit(0)
                if kl == "p":
                    paused = not paused
                    continue
                if kl == "s":
                    _skip_prompts = True
                    print("All future prompts skipped.", flush=True)
                    return
                print("Countdown skipped.", flush=True)
                return

            if not paused:
                time.sleep(min(tick, remaining))
            else:
                time.sleep(tick)

        sys.stdout.write(" " * longest_line + "\r")
        sys.stdout.write("Resuming now.\n")
        sys.stdout.flush()

    finally:
        if raw_mode_set and fd is not None and old_settings is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

# ---------------------------------------------------------------------------#
# Interactive pause between turns
# ---------------------------------------------------------------------------#
def interactive_pause(
    turn_counter: int,
    mode: Optional[str] = None,
    sleep_time: float = 3.0,
) -> None:
    global _skip_prompts
    if _skip_prompts:
        return

    mode = (mode or os.getenv("INTERACTIVE_MODE", "prompt")).strip().lower()
    try:
        sleep_time = float(os.getenv("INTERACTIVE_TIMER_SECONDS", sleep_time))
    except ValueError:
        sleep_time = 3.0

    # Prompt mode
    if mode not in ("off", "timer"):
        prompt = (
            f"Turn {turn_counter}: press any key to continue "
            f"(q=quit, s=skip all, p={sleep_time}s timer) "
        )
        sys.stdout.write(prompt)
        sys.stdout.flush()
        try:
            ch = _getch()
            print()
            if not ch:
                logger.debug("stdin not a TTY – continuing automatically.")
                time.sleep(0.5)
                return
            cl = ch.lower()
            if cl == "q":
                print("Quit requested – exiting.")
                sys.exit(0)
            if cl == "s":
                _skip_prompts = True
                print("Future prompts will be skipped.")
                return
            if cl == "p":
                print(f"Timer ({sleep_time}s) started…")
                _interruptible_countdown(sleep_time)
                return
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.error("Prompt error: %s", exc)
            time.sleep(0.5)
        return

    # Timer mode
    if mode == "timer":
        try:
            _interruptible_countdown(sleep_time)
        except Exception as exc:
            logger.error("Timer error: %s", exc)
            time.sleep(0.5)
        return

    # Off mode → no pause
    return

# ---------------------------------------------------------------------------#
# Global exception handler
# ---------------------------------------------------------------------------#
def handle_exception(
    exc_type, exc_value, exc_traceback
):
    if isinstance(exc_value, KeyboardInterrupt):
        print("\nExecution interrupted by user (Ctrl-C).", file=sys.stderr)
        sys.exit(0)

    if isinstance(exc_value, SystemExit):
        raise exc_value

    import traceback
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.error("Unhandled exception:\n%s", tb)
    print(
        "\nAn unexpected error occurred. "
        "Please check logs or run with higher verbosity for details.",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------#
# Banner‐aware TyperGroup & Global Callback
# ---------------------------------------------------------------------------#
VERSION = "1.1.0"

class BannerGroup(typer.core.TyperGroup):
    def get_help(self, ctx: Context) -> str:
        if sys.stdout.isatty() and not _no_banner:
            banner()
        return super().get_help(ctx)

    def main(self, *args, **kwargs):
        try:
            return super().main(*args, **kwargs)
        except click.ClickException as exc:
            if sys.stdout.isatty() and not _no_banner:
                banner()
            exc.show()
            ctx = self.make_context(self.name, list(args), resilient_parsing=True)
            click.echo(self.get_help(ctx))
            raise typer.Exit(1)

def global_callback(
    ctx: Context,
    version: bool = Option(False, "--version", "-v", help="Print CLI version"),
    debug:   bool = Option(False, "--debug", "-d", help="Enable debug output"),
    no_banner: bool = Option(False, "--no-banner", help="Suppress banner"),
    timeout: Optional[float] = Option(None, "--timeout", "-t", help="Global HTTP timeout in seconds"),
):
    # Debug logging?
    if debug:
        logger.setLevel(logging.DEBUG)

    # Suppress banner?
    if no_banner:
        set_no_banner(True)

    # Global HTTP timeout?
    if timeout is not None:
        set_http_timeout(timeout)

    # Version request?
    if version:
        if sys.stdout.isatty() and not _no_banner:
            banner()
        typer.echo(f"Solvin Agentic OS CLI v{VERSION}")
        raise typer.Exit()

    # No subcommand → show help
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()
