# modules/cli_configs.py

import os
import sys
import json
import requests
import typer
import yaml
import click
from click.exceptions import UsageError

CONFIG_KEY = "SERVICE_URL_CONFIGS"
DEFAULT_API_URL = "http://localhost:8010"
DEFAULT_SCOPE = "global"

def load_config_file():
    entrypoint_path = os.path.abspath(sys.argv[0])
    entrypoint_dir = os.path.dirname(entrypoint_path)
    config_file = os.path.join(entrypoint_dir, ".config.yml")
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            data = yaml.safe_load(f)
            return data or {}
    return {}

def resolve_api_url(api_url_opt: str) -> str:
    # Priority: explicit param > env > .config.yml > default
    if api_url_opt and api_url_opt != DEFAULT_API_URL:
        return api_url_opt
    env_url = os.environ.get(CONFIG_KEY)
    if env_url:
        return env_url
    conf = load_config_file()
    yml_url = conf.get(CONFIG_KEY)
    if yml_url:
        return yml_url
    return DEFAULT_API_URL

app = typer.Typer(invoke_without_command=True, add_completion=False)

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Solvin Configs CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        raise typer.Exit()

@app.command("list")
def list_config(
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
    scope: str = typer.Option(DEFAULT_SCOPE, help="Scope: 'global' or 'service.<service>'"),
):
    """List all config entries in a scope (/config/list)."""
    url = resolve_api_url(api_url)
    typer.echo(f"Listing config entries in scope: {scope}", err=True)
    r = requests.get(f"{url}/config/list", params={"scope": scope})
    if not r.ok:
        typer.secho(r.text, fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))

@app.command("get")
def get_config(
    key: str = typer.Argument(..., help="Config key"),
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
    scope: str = typer.Option(DEFAULT_SCOPE, help="Scope: 'global' or 'service.<service>'"),
):
    """Get a config entry (/config/get)."""
    url = resolve_api_url(api_url)
    r = requests.get(f"{url}/config/get", params={"key": key, "scope": scope})
    if not r.ok:
        typer.secho(r.text, fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))

@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Config key"),
    value: str = typer.Argument(..., help="Config value"),
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
    scope: str = typer.Option(DEFAULT_SCOPE, help="Scope: 'global' or 'service.<service>'"),
):
    """Set (add/update) a config entry (/config/set)."""
    url = resolve_api_url(api_url)
    r = requests.post(
        f"{url}/config/set",
        json={"key": key, "value": value, "scope": scope}
    )
    if not r.ok:
        typer.secho(r.text, fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))

@app.command("remove")
def remove_config(
    keys: str = typer.Argument(..., help="Config key or comma‐delimited keys"),
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
    scope: str = typer.Option(DEFAULT_SCOPE, help="Scope: 'global' or 'service.<service>'"),
):
    """Remove one or more config entries (/config/remove)."""
    url = resolve_api_url(api_url)
    key_list = [k.strip() for k in keys.split(',') if k.strip()]
    results = []
    for key in key_list:
        r = requests.delete(
            f"{url}/config/remove",
            params={"key": key, "scope": scope}
        )
        if not r.ok:
            typer.secho(f"{key}: {r.text}", fg="red", err=True)
            results.append((key, False))
        else:
            typer.echo(f"{key}: removed")
            results.append((key, True))
    failed = [k for k, v in results if not v]
    if failed:
        raise typer.Exit(1)

@app.command("remove-all")
def remove_all_config(
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
    scope: str = typer.Option(DEFAULT_SCOPE, help="Scope: 'global' or 'service.<service>'"),
):
    """Remove ALL config entries in a given scope (/config/remove_all)."""
    url = resolve_api_url(api_url)
    r = requests.delete(f"{url}/config/remove_all", params={"scope": scope})
    if not r.ok:
        typer.secho(r.text, fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))

@app.command("bulk-get")
def bulk_get_config(
    keys: str = typer.Argument(..., help="Comma‐delimited keys (e.g. foo,bar)"),
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
    scope: str = typer.Option(DEFAULT_SCOPE, help="Scope: 'global' or 'service.<service>'"),
):
    """Bulk get config entries (/config/bulk_get)."""
    url = resolve_api_url(api_url)
    key_list = [k.strip() for k in keys.split(',') if k.strip()]
    r = requests.post(f"{url}/config/bulk_get", json={"keys": key_list, "scope": scope})
    if not r.ok:
        typer.secho(r.text, fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))

@app.command("bulk-set")
def bulk_set_config(
    items: str = typer.Argument(..., help="JSON of {key:value,...}"),
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
    scope: str = typer.Option(DEFAULT_SCOPE, help="Scope: 'global' or 'service.<service>'"),
):
    """Bulk set config entries (/config/bulk_set)."""
    url = resolve_api_url(api_url)
    try:
        obj = json.loads(items)
    except Exception:
        typer.secho("Could not parse argument as JSON object.", fg="red", err=True)
        raise typer.Exit(1)
    r = requests.post(f"{url}/config/bulk_set", json={"items": obj, "scope": scope})
    if not r.ok:
        typer.secho(r.text, fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))

@app.command("remove-many")
def remove_many_config(
    keys: str = typer.Argument(..., help="Comma‐delimited keys, e.g. foo,bar"),
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
    scope: str = typer.Option(DEFAULT_SCOPE, help="Scope: 'global' or 'service.<service>'"),
):
    """Remove multiple config entries in a single request (/config/remove_many)."""
    url = resolve_api_url(api_url)
    key_list = [k.strip() for k in keys.split(',') if k.strip()]
    r = requests.delete(f"{url}/config/remove_many", json={"keys": key_list, "scope": scope})
    if not r.ok:
        typer.secho(r.text, fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(r.json(), indent=2))

@app.command("health")
def health(
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
):
    """Liveness/readiness probe (/health)."""
    url = resolve_api_url(api_url)
    try:
        r = requests.get(f"{url}/health")
        if not r.ok:
            typer.secho(json.dumps({"error": f"{r.status_code} {r.text}"}), fg="red", err=True)
            raise typer.Exit(1)
        typer.echo(json.dumps(r.json(), indent=2))
    except Exception as e:
        typer.secho(json.dumps({"error": str(e)}), fg="red", err=True)
        raise typer.Exit(1)

@app.command("scopes")
def scopes(
    api_url: str = typer.Option(DEFAULT_API_URL, help="Config service base URL"),
):
    """List all config scopes (/config/scopes)."""
    url = resolve_api_url(api_url)
    try:
        r = requests.get(f"{url}/config/scopes")
        if not r.ok:
            typer.secho(json.dumps({"error": f"{r.status_code} {r.text}"}), fg="red", err=True)
            raise typer.Exit(1)
        typer.echo(json.dumps(r.json(), indent=2))
    except Exception as e:
        typer.secho(json.dumps({"error": str(e)}), fg="red", err=True)
        raise typer.Exit(1)

def print_command_help_for_argv():
    import click
    ctx = click.get_current_context(silent=True)
    if ctx is not None:
        click.echo(ctx.get_help())
    else:
        click.echo(app.get_help())

if __name__ == "__main__":
    try:
        app(prog_name="solvin configs")
    except UsageError as exc:
        print_command_help_for_argv()
        print(f"\nError: {exc}\n", file=sys.stderr)
        raise typer.Exit(2)
