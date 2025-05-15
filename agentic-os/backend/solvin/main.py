#!/usr/bin/env python3
# solvin/main.py (entrypoint for `solvin`)

import sys
import typer

from modules.cli_errorhandler import bannering_handle_exception
from modules.cli_core import BannerGroup, global_callback

# install our excepthook so uncaught exceptions also get a banner
sys.excepthook = bannering_handle_exception

# import your sub-apps (any import-time error goes through bannering_handle_exception)
try:
    from modules import cli_agents, cli_tools, cli_repos, cli_configs
except Exception:
    bannering_handle_exception(*sys.exc_info())

# -- build the root app --
app = typer.Typer(
    name="solvin",
    help="Agentic OS CLI – Unified entrypoint for all microservices",
    cls=BannerGroup,
    invoke_without_command=True,
    no_args_is_help=True,
    rich_markup_mode="plain",   # ← disable Rich help
)

# register global flags
app.callback(invoke_without_command=True)(global_callback)

# mount each namespace
for sub_app, name, desc in [
    (cli_agents.app,  "agents",  "Manage running agents"),
    (cli_tools.app,   "tools",   "Manage tools"),
    (cli_repos.app,   "repos",   "Manage repos"),
    (cli_configs.app, "configs", "Manage configs"),
]:
    app.add_typer(
        sub_app,
        name=name,
        help=desc,
    )

def main():
    app()

if __name__ == "__main__":
    main()
