#!/usr/bin/env python3
# solvin/main.py (entrypoint for `solvin`)

import sys
import typer

from modules.cli_errorhandler import bannering_handle_exception
from modules.cli_core      import BannerGroup, global_callback
import modules.cli_agents   # these imports will go through your excepthook
import modules.cli_tools
import modules.cli_repos
import modules.cli_configs

# install our excepthook so *any* uncaught exception* prints banner + traceback
sys.excepthook = bannering_handle_exception

app = typer.Typer(
    name="solvin",
    help="Agentic OS CLI – Unified entrypoint for all microservices",
    cls=BannerGroup,                         # <— use BannerGroup here
    invoke_without_command=True,
    no_args_is_help=True,
    rich_markup_mode="plain",
)

# register global flags (version, debug, no-banner, timeout)
app.callback(invoke_without_command=True)(global_callback)

# mount sub-apps
app.add_typer(modules.cli_agents.app,  name="agents",  help="Manage running agents")
app.add_typer(modules.cli_tools.app,   name="tools",   help="Manage tools")
app.add_typer(modules.cli_repos.app,   name="repos",   help="Manage repos")
app.add_typer(modules.cli_configs.app, name="configs", help="Manage configs")

def main():
    app()

if __name__ == "__main__":
    main()
