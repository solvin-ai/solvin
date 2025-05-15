# modules/cli_core/utils.py

import sys
import os
import select
import time
import logging
from typing import Optional

# ——— Banner control —————————————————————————————
_no_banner = False

def set_no_banner(flag: bool) -> None:
    """
    Globally suppress future banner() calls when flag is True.
    """
    global _no_banner
    _no_banner = bool(flag)

def banner() -> None:
    """
    Print the ASCII banner only when stdout is a TTY and not suppressed.
    """
    if _no_banner or not sys.stdout.isatty():
        return
    sys.stdout.write(r"""
 ____        _       _
/ ___|  ___ | |_   _(_)_ __
\___ \ / _ \| \ \ / / | '_ \
 ___) | (_) | |\ V /| | | | |
|____/ \___/|_| \_/ |_|_| |_|

""")
    sys.stdout.flush()

# ——— HTTP timeout global —————————————————————————
_http_timeout: Optional[float] = None

def set_http_timeout(sec: float) -> None:
    """
    Set a global timeout (in seconds) for all downstream HTTP requests.
    """
    global _http_timeout
    _http_timeout = sec

def get_http_timeout() -> Optional[float]:
    """
    Returns the global HTTP timeout (or None if unset).
    """
    return _http_timeout

# Monkey‐patch requests.Session.request to inject our timeout by default
try:
    import requests

    _orig_request = requests.Session.request

    def _timeout_request(self, method, url, *args, **kwargs):
        if "timeout" not in kwargs and _http_timeout is not None:
            kwargs["timeout"] = _http_timeout
        return _orig_request(self, method, url, *args, **kwargs)

    requests.Session.request = _timeout_request

except ImportError:
    # requests not installed → skip
    pass

# ——— Logging fallback ————————————————————————————
try:
    from modules.logs import logger
except ImportError:
    logger = logging.getLogger("cli_core")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

# ——— Platform detection for single-char input ——————————————————
try:
    import msvcrt
    WINDOWS = True
except ImportError:
    WINDOWS = False
    import tty
    import termios

def _getch() -> str:
    """
    Read a single character from stdin (blocking).
    """
    if WINDOWS:
        return msvcrt.getch().decode("utf-8", "ignore")
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        return ""
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def _getch_nonblocking() -> Optional[str]:
    """
    Attempt to read a single character without blocking; return None if none available.
    """
    if WINDOWS:
        return msvcrt.getch().decode("utf-8", "ignore") if msvcrt.kbhit() else None
    dr, _, _ = select.select([sys.stdin], [], [], 0)
    if dr and sys.stdin in dr:
        return sys.stdin.read(1)
    return None

def _interruptible_countdown(total_seconds: float) -> None:
    """
    Countdown timer that can be paused (p), quit (q), or skipped (s).
    """
    remaining = float(total_seconds)
    paused = False
    start = time.monotonic()
    longest = 0

    while remaining > 0:
        now = time.monotonic()
        if not paused:
            remaining = total_seconds - (now - start)
            msg = f"Continuing in {int(remaining)+1}s (p=pause, q=quit, s=skip)"
        else:
            msg = "Paused (p=resume, q=quit, s=skip)"
        sys.stdout.write(f"{msg:<{longest}}\r")
        sys.stdout.flush()
        longest = max(longest, len(msg))

        key = _getch_nonblocking()
        if key:
            sys.stdout.write(" " * longest + "\r")
            sys.stdout.flush()
            kl = key.lower()
            if kl == "q":
                sys.exit(0)
            if kl == "p":
                paused = not paused
                if not paused:
                    start = time.monotonic()
                continue
            if kl == "s":
                print("Skipped.", flush=True)
                return
        time.sleep(0.1)

    sys.stdout.write("\n")

def interactive_pause(turn: int, mode: Optional[str] = None, sleep_time: float = 3.0) -> None:
    """
    Pause interactively between turns. Modes: 'prompt' (default), 'timer', or 'off'.
    """
    mode = (mode or os.getenv("INTERACTIVE_MODE", "prompt")).lower()
    if mode not in ("off", "timer"):
        prompt = (
            f"Turn {turn}: press any key "
            f"(q=quit, s=skip, p={sleep_time}s timer) "
        )
        sys.stdout.write(prompt)
        sys.stdout.flush()
        ch = _getch()
        print()
        if not ch:
            return
        cl = ch.lower()
        if cl == "q":
            sys.exit(0)
        if cl == "s":
            return
        if cl == "p":
            print(f"Timer {sleep_time}s…")
            _interruptible_countdown(sleep_time)
        return

    if mode == "timer":
        try:
            _interruptible_countdown(sleep_time)
        except Exception:
            pass
    # mode == "off": do nothing
