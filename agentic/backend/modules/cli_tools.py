# modules/cli_tools.py

import sys
import json
import requests
import typer
from typing import List, Optional, Dict, Any

from shared.config import config
config["SERVICE_NAME"] = "cli"

from shared.logger import logger
from modules.cli_core import banner

from shared.client_tools import execute_tool as nats_execute_tool, execute_tool_bulk as nats_execute_tool_bulk

API_VERSION = "v1"
API_PREFIX  = f"/api/{API_VERSION}"

app = typer.Typer(
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


class ToolsClient:
    """
    Minimal wrapper around the Tools HTTP API for non‐execution commands.
    Honors the --api-url override in the CLI.
    Unwraps the standard {status,data,error} envelope.
    """

    def __init__(self, base_url: str):
        # strip trailing slash, then add our /api/v1 prefix
        self.base    = base_url.rstrip("/") + API_PREFIX
        self.headers = {"Content-Type": "application/json"}

    def _unwrap(self, resp: requests.Response):
        # 1) HTTP‐level errors
        resp.raise_for_status()
        # 2) parse envelope
        try:
            env = resp.json()
        except ValueError as e:
            logger.error("Invalid JSON response from %s: %s", resp.url, e)
            typer.secho(f"Error: Invalid JSON response from {resp.url}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        # 3) RPC‐level error?
        if env.get("status") == "error":
            err = env.get("error") or {}
            msg = err.get("message", "<no message>")
            typer.secho(f"Error: {msg}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        # 4) success → return data
        return env.get("data")

    def health_check(self):
        r = requests.get(f"{self.base}/health", headers=self.headers)
        return self._unwrap(r)

    def ready_check(self):
        r = requests.get(f"{self.base}/ready", headers=self.headers)
        return self._unwrap(r)

    def status(self):
        r = requests.get(f"{self.base}/status", headers=self.headers)
        return self._unwrap(r)

    def list_tools(self):
        r = requests.get(f"{self.base}/tools/list", headers=self.headers)
        return self._unwrap(r)

    def tools_info(
        self,
        tool_name: Optional[str] = None,
        tool_names: Optional[List[str]] = None,
        meta: bool = True,
        schema: bool = True
    ):
        """
        - single‐tool lookup: GET  /tools/info?tool_name=foo&meta=true&schema=true
        - bulk lookup:         POST /tools/info?meta=true&schema=true  { "tool_names": [...] }
        """
        url = f"{self.base}/tools/info"
        params = {"meta": meta, "schema": schema}

        if tool_names:
            payload = {"tool_names": tool_names}
            r = requests.post(url, params=params, json=payload, headers=self.headers)
        elif tool_name:
            params["tool_name"] = tool_name
            r = requests.get(url, params=params, headers=self.headers)
        else:
            raise typer.BadParameter("Must supply --tool-name or --tool-names")

        return self._unwrap(r)


@app.callback()
def main(
    ctx: typer.Context,
    api_url: Optional[str] = typer.Option(
        None,
        "--api-url",
        help="Override Tools API URL (for HTTP commands)",
    ),
):
    """
    Solvin tools CLI
    """
    if api_url:
        ctx.obj = {"api_url": api_url}
    else:
        default   = "http://localhost:8001"
        tools_url = config.get("SERVICE_URL_TOOLS", default=default)
        ctx.obj   = {"api_url": tools_url}

    # show the banner only on interactive runs
    if sys.stdout.isatty():
        banner()


@app.command("health")
def cmd_health(ctx: typer.Context):
    "Health check of the tools service."
    client = ToolsClient(ctx.obj["api_url"])
    typer.echo(json.dumps(client.health_check(), indent=2))


@app.command("ready")
def cmd_ready(ctx: typer.Context):
    "Ready check of the tools service."
    client = ToolsClient(ctx.obj["api_url"])
    typer.echo(json.dumps(client.ready_check(), indent=2))


@app.command("status")
def cmd_status(ctx: typer.Context):
    "Get service status (requests count, uptime, version, etc.)."
    client = ToolsClient(ctx.obj["api_url"])
    typer.echo(json.dumps(client.status(), indent=2))


@app.command("list")
def cmd_list(ctx: typer.Context):
    "List available tools and metadata."
    client = ToolsClient(ctx.obj["api_url"])
    typer.echo(json.dumps(client.list_tools(), indent=2))


@app.command("info")
def cmd_info(
    ctx: typer.Context,
    names: List[str] = typer.Argument(
        None,
        metavar="NAMES",
        help="Tool name(s), comma separated or as multiple arguments."
    ),
    meta: bool = typer.Option(True, "--meta/--no-meta", help="Include metadata"),
    schema: bool = typer.Option(True, "--schema/--no-schema", help="Include schema"),
):
    """
    Get metadata/schema info for one or more tools.
    """
    effective_names: List[str] = []
    for entry in names or []:
        effective_names.extend(n.strip() for n in entry.split(",") if n.strip())

    if not effective_names:
        typer.secho("Error: At least one tool name must be provided.",
                    fg=typer.colors.RED, err=True)
        typer.echo(cmd_info.get_help(ctx))
        raise typer.Exit(1)

    client = ToolsClient(ctx.obj["api_url"])
    result = client.tools_info(tool_names=effective_names, meta=meta, schema=schema)
    typer.echo(json.dumps(result, indent=2))


@app.command("execute")
def cmd_execute(
    tool_name: str,
    repo_name: str,
    input_args_file: str = typer.Argument(..., help="JSON file with input args"),
    repo_owner: Optional[str] = typer.Option(None, "--repo-owner", help="Optional repo owner"),
    metadata_file: Optional[str] = typer.Option(None, "--metadata-file", help="JSON file with metadata"),
    turn_id: Optional[str] = typer.Option(None, help="Turn id"),
):
    """
    Enqueue a tool execution request (non‐blocking) via NATS JetStream.
    """
    try:
        with open(input_args_file) as f:
            input_args = json.load(f)
    except Exception as e:
        typer.secho(f"Error reading input args file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    metadata: Optional[Dict[str, Any]] = None
    if metadata_file:
        try:
            with open(metadata_file) as mf:
                metadata = json.load(mf)
        except Exception as e:
            typer.secho(f"Error reading metadata file: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

    try:
        result = nats_execute_tool(
            tool_name=tool_name,
            input_args=input_args,
            repo_name=repo_name,
            repo_owner=repo_owner,
            metadata=metadata,
            turn_id=turn_id,
        )
    except Exception as e:
        typer.secho(f"Error enqueuing execution request: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    typer.echo(json.dumps(result, indent=2))


@app.command("execute-bulk")
def cmd_execute_bulk(
    requests_file: str = typer.Argument(..., help="JSON file with a list of execution requests"),
):
    """
    Enqueue multiple tool execution requests (non‐blocking) via NATS JetStream.
    """
    try:
        with open(requests_file) as f:
            requests_list = json.load(f)
    except Exception as e:
        typer.secho(f"Error reading requests file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    try:
        result = nats_execute_tool_bulk(requests_list)
    except Exception as e:
        typer.secho(f"Error enqueuing bulk execution requests: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
