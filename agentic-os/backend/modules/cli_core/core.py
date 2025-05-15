# modules/cli_core/core.py

import os
import sys
import logging
import click
import typer
from typer import Context, Option

from .utils import banner, set_no_banner, set_http_timeout

VERSION = "1.1.0"
logger = logging.getLogger("cli_core")


class BannerGroup(typer.core.TyperGroup):
    def __init__(self, *args, **kwargs):
        # always invoke the global callback (even if no subcommand)
        kwargs.setdefault("invoke_without_command", True)
        # let bare `solvin` print help
        kwargs.setdefault("no_args_is_help", True)
        super().__init__(*args, **kwargs)

    def format_help(self, ctx: Context, formatter: click.formatting.HelpFormatter):
        """
        Always called when Click/Typer is about to render help,
        whether via --help, no-args, or after a parse error.
        We print our banner first, then let Click render into the formatter.
        """
        if sys.stdout.isatty():
            banner()
        super().format_help(ctx, formatter)

    def main(self, *args, **kwargs):
        """
        Wrap the normal Typer main so that on parse errors we print
        banner + error + help and exit(1).
        """
        try:
            return super().main(*args, **kwargs)
        except click.ClickException as exc:
            # re-raise normal Exit(0) (help, ctx.exit)
            if isinstance(exc, click.exceptions.Exit):
                raise
            # on any other ClickException: banner + error + help + exit(1)
            if sys.stdout.isatty():
                banner()
            exc.show()
            sub_ctx = self.make_context(self.name, list(args), resilient_parsing=True)
            click.echo(self.get_command_help(sub_ctx), err=True)
            sys.exit(1)

    def get_command_help(self, ctx: Context) -> str:
        """
        Render and return the help text for ctx.command at ctx,
        using a fixed-width formatter.
        """
        fmt = click.formatting.HelpFormatter(width=80)
        super().format_help(ctx, fmt)
        return fmt.getvalue()


def global_callback(
    ctx: Context,
    version:   bool          = Option(False, "--version", "-v", help="Show version"),
    debug:     bool          = Option(False, "--debug",   "-d", help="Enable debug output"),
    no_banner: bool          = Option(False, "--no-banner",    help="Suppress banner"),
    timeout:   float | None  = Option(None,     "--timeout", "-t", help="Global HTTP timeout"),
):
    # 0) Check SOLVIN_DEBUG environment variable
    env = os.getenv("SOLVIN_DEBUG", "").lower()
    if not debug and env in ("1", "true", "yes"):
        debug = True

    # 1) --debug or SOLVIN_DEBUG
    if debug:
        import modules.cli_errorhandler as _errhdl  # defer import to avoid cycle
        logger.setLevel(logging.DEBUG)
        _errhdl.DEBUG = True
        logger.debug("DEBUG mode ON")

    # 2) --no-banner
    if no_banner:
        set_no_banner(True)

    # 3) --timeout
    if timeout is not None:
        set_http_timeout(timeout)
        logger.debug("Global HTTP timeout set to %s seconds", timeout)

    # 4) --version: print banner + version, then exit
    if version:
        if sys.stdout.isatty():
            banner()
        typer.echo(f"Solvin CLI v{VERSION}")
        raise typer.Exit()

    # 5) no subcommand: print banner + root help, then exit
    if ctx.invoked_subcommand is None:
        if sys.stdout.isatty():
            banner()
        typer.echo(ctx.get_help())
        raise typer.Exit()
