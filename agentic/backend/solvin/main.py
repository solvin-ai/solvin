#!/usr/bin/env python3
# main.py (solvin)

import sys

# 1) Install our global exception hook _first_, so import‐time errors
#    (e.g. network failures in sub‐modules) get routed through it.
from modules.cli_errorhandler import bannering_handle_exception
sys.excepthook = bannering_handle_exception

import typer

# BannerGroup & global callback (version/debug/no‐banner/timeout)
from modules.cli_core import BannerGroup, global_callback

# The four sub‐CLIs
from modules import cli_agents, cli_tools, cli_repos, cli_configs

# Create root Typer app with our BannerGroup
app = typer.Typer(
    help="Agentic Swarm CLI – Unified entrypoint for all microservices",
    cls=BannerGroup,
)

# Mount each of the microservice CLIs under its namespace
app.add_typer(cli_agents.app,   name="agents")
app.add_typer(cli_tools.app,    name="tools")
app.add_typer(cli_repos.app,    name="repos")
app.add_typer(cli_configs.app,  name="configs")

# Hook in our single global‐flags callback (handles --version, --debug, --no-banner, --timeout)
app.callback(invoke_without_command=True)(global_callback)

if __name__ == "__main__":
    app()
