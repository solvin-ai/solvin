# modules/cli.py

"""
This module centralizes all command‑line interactions. It includes:
  • Interactive pause logic (prompt, timer with countdown, off).
  • Typer‑based CLI parsing.
  • Global exception and signal handling.
  • Commands to clear various stored data.
  • New service management commands to interface with external services (agentic, config, repos, tools, teams).

Note: This file expects a configuration module (modules.config) with a .get(key, default)
method to look up values such as:
  - SCRIPT_DIR, DATA_DIR, INTERACTIVE_MODE, INTERACTIVE_TIMER_SECONDS
  - AGENTIC_SERVICE_URL      (default: "http://localhost:8000")
  - CONFIG_SERVICE_URL       (default: "http://localhost:8001")
  - REPOS_SERVICE_URL        (default: "http://localhost:8002")
  - TOOLS_SERVICE_URL        (default: "http://localhost:8003")
  - TEAMS_SERVICE_URL        (default: "http://localhost:8004")
  
This file uses Typer to define a command‑line interface.
"""

import sys
import time
import shutil
import traceback
from pathlib import Path
from typing import Optional
import typer
import select
import os
import requests

from modules.logs import logger
from modules.config import config  # Assumes config is loaded and supports .get(key, default)

# --- Platform specific setup ---
try:
    import msvcrt
    WINDOWS = True
except ImportError:
    WINDOWS = False
    import termios
    import tty

# --- Global State ---
SCRIPT_DIR = Path(config.get("SCRIPT_DIR", ".")).resolve()
_skip_prompts = False

# Centralized data paths: use config values or default to {SCRIPT_DIR}/data
DATA_DIR = Path(config.get("DATA_DIR", SCRIPT_DIR / "data")).resolve()
REPOS_DIR = DATA_DIR / "repos"
LOGS_DIR = DATA_DIR / "logs"
THOUGHTS_DIR = DATA_DIR / "thoughts"
REQUESTS_DIR = DATA_DIR / "requests"
STATE_DIR = DATA_DIR / "state"  # Consistent state directory

# --- Terminal Interaction Functions ---

def _getch():
    """
    Capture a single blocking key press. Restores terminal settings on exit.
    """
    if WINDOWS:
        return msvcrt.getch().decode("utf-8", errors="ignore")
    else:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            logger.warning("Standard input is not a TTY. Cannot get single character.")
            return ""
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

def _getch_nonblocking():
    """
    Attempts to capture a single key press without blocking. Returns the key if available.
    """
    if WINDOWS:
        if msvcrt.kbhit():
            return msvcrt.getch().decode("utf-8", errors="ignore")
        return None
    else:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr and sys.stdin in dr:
            try:
                return sys.stdin.read(1)
            except Exception as e:
                logger.debug(f"Error reading from stdin after select: {e}")
                return None
        return None

def _interruptible_countdown(total_seconds: float):
    """
    Performs an interruptible countdown.

    During the countdown:
      - Pressing 'q' exits the program.
      - Pressing 'p' toggles pause/resume.
      - Pressing 's' cancels the prompt for all subsequent turns.
      - Pressing any other key skips the wait for the current turn.
    """
    global _skip_prompts
    remaining = float(total_seconds)
    paused = False
    interval = 0.1  # seconds

    fd = None
    old_settings = None
    set_mode_success = False

    if not WINDOWS and sys.stdin.isatty():
        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            set_mode_success = True
            logger.debug("Terminal set to cbreak mode for countdown.")
        except Exception as e:
            logger.warning(f"Could not set terminal to cbreak mode: {e}")

    try:
        start_time = time.monotonic()
        pause_start_time = None
        prompt_line_len = 0

        while remaining > 0:
            current_time = time.monotonic()

            if paused:
                if pause_start_time is None:
                    pause_start_time = current_time
                status_msg = "Countdown paused. Press 'p' to resume, 'q' to quit, 's' to skip all, any other to skip now..."
                print(f"{status_msg:<{prompt_line_len}}", end="\r", flush=True)
                prompt_line_len = max(prompt_line_len, len(status_msg))
            else:
                if pause_start_time is not None:
                    pause_duration = current_time - pause_start_time
                    start_time += pause_duration
                    pause_start_time = None
                elapsed_time = current_time - start_time
                remaining = total_seconds - elapsed_time
                if remaining <= 0:
                    break
                status_msg = f"Resuming in {int(remaining)+1} seconds... (p=pause, q=quit, s=skip all, other=skip now)"
                print(f"{status_msg:<{prompt_line_len}}", end="\r", flush=True)
                prompt_line_len = max(prompt_line_len, len(status_msg))

            key = _getch_nonblocking()
            if key is not None:
                key_lower = key.lower()
                print(" " * prompt_line_len, end="\r", flush=True)
                if key_lower == 'q':
                    logger.info("Exiting during countdown as 'q' was pressed.")
                    sys.exit(0)
                elif key_lower == 'p':
                    paused = not paused
                    continue
                elif key_lower == 's':
                    _skip_prompts = True
                    print("Prompt cancelled for all subsequent turns.", flush=True)
                    return
                else:
                    print("Countdown interrupted, skipping wait.", flush=True)
                    return

            if not paused:
                sleep_duration = min(interval, remaining) if remaining > 0 else interval
                time.sleep(sleep_duration)
            else:
                time.sleep(interval)
        print(" " * prompt_line_len, end="\r", flush=True)
        print("Resuming now.", flush=True)
    finally:
        if set_mode_success and fd is not None and old_settings is not None:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                logger.debug("Terminal settings restored.")
            except Exception as e:
                logger.error(f"Failed to restore terminal settings: {e}")

# --- Banner, Exception Handling, Interactive Pause ---

def banner():
    """
    Print a multi-line banner.
    """
    banner_text = r"""
 ____        _       _
/ ___|  ___ | |_   _(_)_ __
\___ \ / _ \| \ \ / / | '_ \
 ___) | (_) | |\ V /| | | | |
|____/ \___/|_| \_/ |_|_| |_|
"""
    print(banner_text)

def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Global exception handler. Logs errors and handles graceful exit.
    """
    if isinstance(exc_value, KeyboardInterrupt):
        print("\nExecution interrupted by the user (Ctrl+C). Exiting gracefully.", file=sys.stderr)
        sys.exit(0)
    elif isinstance(exc_value, SystemExit):
        raise exc_value
    else:
        stack_trace = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.error("Unhandled exception occurred:\n%s", stack_trace)
        print("\nAn unexpected error occurred. Please check the log file for details.", file=sys.stderr)
        sys.exit(1)

sys.excepthook = handle_exception

def interactive_pause(turn_counter: int):
    """
    Pause execution between turns based on the INTERACTIVE_MODE setting.
    """
    global _skip_prompts
    if _skip_prompts:
        logger.debug(f"Turn {turn_counter}: Skipping prompt.")
        return

    mode = config.get("INTERACTIVE_MODE", "prompt").strip().lower()
    sleep_time = float(config.get("INTERACTIVE_TIMER_SECONDS", 3.0))
    if mode == "timer":
        logger.debug(f"Turn {turn_counter}: Starting {sleep_time}s timer pause.")
        try:
            _interruptible_countdown(sleep_time)
        except Exception as e:
            logger.error(f"Error during timer countdown: {e}")
            print("\nError during timer, continuing automatically...", file=sys.stderr)
            time.sleep(0.5)
    elif mode == "prompt" or mode != "off":
        logger.debug(f"Turn {turn_counter}: Waiting for user prompt.")
        try:
            prompt_msg = f"Turn {turn_counter}: Press any key to continue (q=quit, s=skip all prompts, p=start {sleep_time}s timer): "
            print(prompt_msg, end="", flush=True)
            user_in = _getch()
            print()
            if not user_in:
                logger.warning("Could not read from TTY in prompt mode. Continuing automatically.")
                time.sleep(0.5)
                return
            user_in_lower = user_in.lower()
            if user_in_lower == "q":
                logger.info(f"Exiting at turn {turn_counter} per user request ('q' pressed).")
                sys.exit(0)
            elif user_in_lower == "s":
                _skip_prompts = True
                print("Prompts skipped for all subsequent turns. Continuing...")
                logger.info("Prompts skipped via 's' key.")
                return
            elif user_in_lower == "p":
                print(f"Starting {sleep_time} second timer pause (interruptible)...")
                logger.debug("User pressed 'p', starting timer pause.")
                try:
                    _interruptible_countdown(sleep_time)
                except Exception as e:
                    logger.error(f"Error during timer countdown triggered by 'p': {e}")
                    print("\nError during timer, continuing automatically...", file=sys.stderr)
                    time.sleep(0.5)
            else:
                logger.debug(f"User pressed '{user_in}', continuing.")
                return
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error(f"Error during prompt mode: {e}")
            print(f"\nError during prompt ({e}), continuing automatically...", file=sys.stderr)
            time.sleep(1)
    elif mode == "off":
        logger.debug(f"Turn {turn_counter}: Interactive mode off, proceeding.")

# --- Typer CLI Application ---

# Callback function placeholder to be set by main script.
_run_callback = None

def register_run_callback(callback):
    """
    Registers a callback to run the main pipeline.
    """
    global _run_callback
    _run_callback = callback

# Main Typer application instance
app = typer.Typer(
    help="Agentic Swarm CLI - Run code generation pipelines.",
    no_args_is_help=True,
    add_completion=False,
)

# --- New Services Management Commands ---
services_app = typer.Typer(help="Manage external services via their API endpoints.")

@services_app.command("health")
def service_health(
    service: str = typer.Option(..., "--service", "-s", help="Service to check: agentic, config, repos, tools, teams")
):
    """
    Check the health of a given service.
    """
    mapping = {
        "agentic": config.get("AGENTIC_SERVICE_URL", "http://localhost:8000"),
        "config": config.get("CONFIG_SERVICE_URL", "http://localhost:8001"),
        "repos": config.get("REPOS_SERVICE_URL", "http://localhost:8002"),
        "tools": config.get("TOOLS_SERVICE_URL", "http://localhost:8003"),
        "teams": config.get("TEAMS_SERVICE_URL", "http://localhost:8004"),
    }
    svc_key = service.lower()
    if svc_key not in mapping:
        typer.echo(f"Unknown service '{service}'. Choose from: {', '.join(mapping.keys())}")
        raise typer.Exit(code=1)
    url = mapping[svc_key].rstrip("/") + "/health"
    try:
        response = requests.get(url)
        response.raise_for_status()
        typer.echo(f"{svc_key.capitalize()} service health: {response.json()}")
    except Exception as e:
        typer.echo(f"Error checking health for {svc_key} service: {e}")

@services_app.command("list-agents")
def list_agents():
    """
    List agents via the agentic service.
    """
    url = config.get("AGENTIC_SERVICE_URL", "http://localhost:8000").rstrip("/") + "/agents/list"
    try:
        response = requests.get(url)
        response.raise_for_status()
        agents = response.json()
        typer.echo(agents)
    except Exception as e:
        typer.echo(f"Error listing agents: {e}")

@services_app.command("list-turns")
def list_turns():
    """
    List conversation turns via the agentic service.
    """
    url = config.get("AGENTIC_SERVICE_URL", "http://localhost:8000").rstrip("/") + "/turns/list"
    try:
        response = requests.get(url)
        response.raise_for_status()
        turns = response.json()
        typer.echo(turns)
    except Exception as e:
        typer.echo(f"Error listing turns: {e}")

@services_app.command("list-tools")
def list_tools():
    """
    List tools via the tools service.
    """
    url = config.get("TOOLS_SERVICE_URL", "http://localhost:8003").rstrip("/") + "/tools/list"
    try:
        response = requests.get(url)
        response.raise_for_status()
        tools = response.json()
        typer.echo(tools)
    except Exception as e:
        typer.echo(f"Error listing tools: {e}")

@services_app.command("list-repos")
def list_repos():
    """
    List repositories via the repos service.
    """
    url = config.get("REPOS_SERVICE_URL", "http://localhost:8002").rstrip("/") + "/repos/list"
    try:
        response = requests.get(url)
        response.raise_for_status()
        repos = response.json()
        typer.echo(repos)
    except Exception as e:
        typer.echo(f"Error listing repositories: {e}")

@services_app.command("list-config")
def list_config():
    """
    List configuration entries via the config service.
    """
    url = config.get("CONFIG_SERVICE_URL", "http://localhost:8001").rstrip("/") + "/config/list"
    try:
        response = requests.get(url)
        response.raise_for_status()
        entries = response.json()
        typer.echo(entries)
    except Exception as e:
        typer.echo(f"Error listing configuration entries: {e}")

# Add the services_app group to the main Typer app as “service”
app.add_typer(services_app, name="service")

# --- Clear Commands ---

clear_app = typer.Typer(help="Commands to clear various stored data.", no_args_is_help=True)
app.add_typer(clear_app, name="clear")

def _clear_directory_contents(dir_path: Path, dir_description: str):
    if not dir_path.is_dir():
         logger.warning(f"Directory '{dir_description}' ({dir_path}) not found for clearing. Skipping.")
         print(f"Directory '{dir_description}' not found: {dir_path}")
         return False
    logger.info(f"Clearing contents of '{dir_description}' directory: '{dir_path}'")
    print(f"Clearing contents of {dir_description}: {dir_path} ...")
    cleared_count = 0
    error_count = 0
    for child in dir_path.iterdir():
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
                logger.debug(f"Deleted file/link: {child}")
                cleared_count += 1
            elif child.is_dir():
                shutil.rmtree(child)
                logger.debug(f"Deleted directory: {child}")
                cleared_count += 1
        except Exception as e:
            logger.error(f"Failed to remove {child.name} from {dir_path}: {e}")
            print(f"  Error removing {child.name}: {e}", file=sys.stderr)
            error_count += 1
    if error_count > 0:
        logger.warning(f"Finished clearing '{dir_description}', encountered {error_count} errors.")
        print(f"Finished clearing {dir_description} with {error_count} errors.")
    elif cleared_count == 0:
        logger.info(f"Directory '{dir_description}' ({dir_path}) was empty.")
        print(f"Directory '{dir_description}' was empty.")
    else:
        logger.info(f"Cleared {cleared_count} items from '{dir_description}' ({dir_path}).")
        print(f"Successfully cleared {cleared_count} items from {dir_description}.")
    return True

@clear_app.command("state")
def clear_state():
    """Clears the application state directory."""
    logger.info("Executing 'clear state' command.")
    _clear_directory_contents(STATE_DIR, "state")

@clear_app.command("logs")
def clear_logs():
    """Clears all log files in the logs directory."""
    logger.info("Executing 'clear logs' command.")
    _clear_directory_contents(LOGS_DIR, "logs")

@clear_app.command("thoughts")
def clear_thoughts():
    """Clears stored thoughts from the thoughts directory."""
    logger.info("Executing 'clear thoughts' command.")
    _clear_directory_contents(THOUGHTS_DIR, "thoughts")

@clear_app.command("requests")
def clear_requests():
    """Clears stored requests from the requests directory."""
    logger.info("Executing 'clear requests' command.")
    _clear_directory_contents(REQUESTS_DIR, "requests")

@clear_app.command("repos")
def clear_repos():
    """Clears stored repositories from the repos directory."""
    logger.info("Executing 'clear repos' command.")
    _clear_directory_contents(REPOS_DIR, "repositories")

@clear_app.command("all-but-repos")
def clear_all_but_repos():
     """Clears state, logs, thoughts, and requests, leaving repositories intact."""
     logger.info("Executing 'clear all-but-repos' command.")
     print("Clearing all data except repositories...")
     clear_state()
     clear_logs()
     clear_thoughts()
     clear_requests()
     logger.info("Cleared state, logs, thoughts, and requests.")
     print("Finished clearing data (excluding repositories).")

@clear_app.command("all")
def clear_all():
    """
    Clears ALL stored data: state, logs, thoughts, requests, and repositories.
    Use with caution!
    """
    logger.warning("Executing 'clear all' command. This will remove repositories.")
    print("Clearing ALL data including repositories...")
    clear_state()
    clear_logs()
    clear_thoughts()
    clear_requests()
    clear_repos()
    logger.info("Cleared state, logs, thoughts, requests, and repositories.")
    print("Finished clearing ALL data.")

# --- Main Typer Callback ---

@app.callback(invoke_without_command=True)
def main_cli(
    ctx: typer.Context,
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Repository name or Git URL to process."),
    config_file: Path = typer.Option(
        Path(".config.yml"),
        "--config", "-c",
        help="Path to the configuration file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit.", is_eager=True),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode (verbose logging).")
):
    """
    Agentic Swarm CLI Entry Point.

    Processes a target repository based on the provided configuration.
    If no subcommand is invoked, --repo is required.
    """
    if version:
        typer.echo("Agentic Swarm version: 1.0.0")
        raise typer.Exit()
    ctx.ensure_object(dict)
    ctx.obj["DEBUG"] = debug
    ctx.obj["CONFIG_FILE"] = config_file
    if ctx.invoked_subcommand is None:
        if repo:
            banner()
            if _run_callback is not None:
                logger.info(f"Starting main process for repo: {repo}")
                _run_callback(repo=repo, config_file=str(config_file), debug=debug)
            else:
                logger.error("Run callback not registered. Cannot start main process.")
                typer.echo("Error: Main application logic not configured.", err=True)
                raise typer.Exit(code=1)
        else:
            typer.echo("Error: Missing option '--repo' / '-r'.", err=True)
            typer.echo(ctx.get_help())
            raise typer.Exit(code=1)

if __name__ == "__main__":
    print("CLI module running directly. Registering dummy run callback.")

    def dummy_run_callback(**kwargs):
        print("Dummy run callback invoked with:")
        for key, value in kwargs.items():
            print(f"  {key}: {value}")
        interactive_pause(1)
        interactive_pause(2)
        print("Dummy run finished.")

    register_run_callback(dummy_run_callback)
    app()
