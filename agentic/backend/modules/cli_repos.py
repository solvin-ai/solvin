# modules/cli_repos.py

"""
CLI for repository management commands.
This tool uses the ReposClient to interact with the repos service.
"""

import json
import typer
from typing import Optional, Dict, Any

from shared.config import config
config["SERVICE_NAME"] = "cli"

from shared.client_repos import (
    ReposClient,
    ReposClientError,
    ReposClientConflict,
)

# Allow override of the repos‐service URL from config
_api_url = config.get("SERVICE_URL_REPOS", None)
_client_kwargs: Dict[str, Any] = {}
if _api_url:
    _client_kwargs["api_url"] = _api_url

# Optionally override timeout via config (seconds, float or (connect, read))
_timeout = config.get("REPOS_CLIENT_TIMEOUT_SEC", None)
if _timeout is not None:
    _client_kwargs["timeout"] = _timeout

client = ReposClient(**_client_kwargs)

app = typer.Typer(help="Repository management commands.")


def _handle_error(exc: Exception, on_conflict: str = None):
    if isinstance(exc, ReposClientConflict):
        msg = f"Conflict: {exc}"
        typer.secho(msg, fg="yellow")
    elif isinstance(exc, ReposClientError):
        msg = f"Request failed: {exc}"
        typer.secho(msg, fg="red")
    else:
        msg = f"Error: {exc}"
        typer.secho(msg, fg="red")
    raise typer.Exit(code=1)


@app.command("root")
def root():
    """GET / (root health‐check)."""
    try:
        result = client.root()
        typer.echo(json.dumps(result, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("health")
def health():
    """GET /health (liveness)."""
    try:
        result = client.health()
        typer.secho(json.dumps(result, indent=2), fg="green")
    except Exception as e:
        _handle_error(e)


@app.command("ready")
def ready():
    """GET /ready (readiness)."""
    try:
        result = client.ready()
        typer.secho(json.dumps(result, indent=2), fg="green")
    except Exception as e:
        _handle_error(e)


@app.command("status")
def status():
    """GET /status (metrics & status)."""
    try:
        result = client.status()
        typer.echo(json.dumps(result, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("list")
def list_repos():
    """List all repositories."""
    try:
        repos = client.list_repos()
        typer.echo(json.dumps(repos, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("info")
def info(repo_url: str = typer.Argument(..., help="Repository URL")):
    """Show details about a repository."""
    try:
        detail = client.get_repo_info(repo_url)
        typer.echo(json.dumps(detail, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("admit")
def admit(
    repo_url: str = typer.Option(..., "--url", "-u", help="Git URL to clone (https://…git)"),
    team_id: Optional[str] = typer.Option(None, "--team", "-t", help="Owning team ID"),
    priority: int = typer.Option(0, "--priority", "-p", help="Priority (higher → sooner)"),
    default_branch: Optional[str] = typer.Option(None, "--default-branch", "-b", help="Default branch name"),
):
    """
    Clone & admit a repository by URL. Runs the admission pipeline
    (detect language, build system + version, JDK, code stats, etc.).
    """
    typer.echo(f"Admitting repository from URL: {repo_url!r} …")
    try:
        result = client.admit_repo(
            repo_url=repo_url,
            team_id=team_id,
            priority=priority,
            default_branch=default_branch,
        )
        typer.secho("Repository admitted successfully!", fg="green")
        typer.echo(json.dumps(result, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("admit-bulk")
def admit_bulk(
    repos: str = typer.Option(..., "--repos", "-r", help="JSON list of admit payloads")
):
    """
    Bulk admit by URL. Pass a JSON list of objects:
      [{ "repo_url": …, "team_id"?: …, "priority"?: …, "default_branch"?: … }, …]
    """
    try:
        payload = json.loads(repos)
    except json.JSONDecodeError as e:
        typer.secho(f"Invalid JSON for repos list: {e}", fg="red")
        raise typer.Exit(code=1)

    try:
        result = client.admit_bulk(payload)
        typer.secho("Bulk admit successful!", fg="green")
        typer.echo(json.dumps(result, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("add")
def add(
    repo_url: str = typer.Option(..., "--url", "-u", help="Git URL of the repository"),
    repo_name: str = typer.Option(..., "--name", "-n", help="Short name/ID of the repository"),
    repo_owner: str = typer.Option(..., "--owner", "-o", help="Owner (user or org)"),
    team_id: str = typer.Option(..., "--team", "-t", help="Owning team ID"),
    customer_id: Optional[str] = typer.Option(None, "--customer-id", help="Customer ID (DB only)"),
    default_branch: Optional[str] = typer.Option(None, "--default-branch", "-b", help="Default branch name"),
    priority: int = typer.Option(0, "--priority", "-p", help="Priority (higher → sooner)"),
    metadata: str = typer.Option("{}", "--metadata", "-m", help="JSON string of metadata"),
    jdk_version: Optional[str] = typer.Option(None, "--jdk", help="JDK version (if any)"),
):
    """
    Raw‐columns insert: insert a repository record into the database
    with the given URL, name, owner, customer_id, team_id,
    default_branch, priority, metadata JSON, and optional JDK version.
    """
    try:
        md: Dict[str, Any] = json.loads(metadata)
    except json.JSONDecodeError as e:
        typer.secho(f"Invalid JSON for metadata: {e}", fg="red")
        raise typer.Exit(code=1)

    typer.echo(
        f"Adding repository {repo_name!r} at URL {repo_url!r} "
        f"(owner={repo_owner}, team={team_id}) …"
    )
    try:
        result = client.add_repo(
            repo_url=repo_url,
            repo_name=repo_name,
            repo_owner=repo_owner,
            team_id=team_id,
            customer_id=customer_id,
            default_branch=default_branch,
            priority=priority,
            metadata=md,
            jdk_version=jdk_version,
        )
        typer.secho("Repository added successfully!", fg="green")
        typer.echo(json.dumps(result, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("add-bulk")
def add_bulk(
    repos: str = typer.Option(..., "--repos", "-r", help="JSON list of add payloads")
):
    """
    Bulk raw‐columns insert. Pass a JSON list of objects matching add_repo’s payload.
    """
    try:
        payload = json.loads(repos)
    except json.JSONDecodeError as e:
        typer.secho(f"Invalid JSON for repos list: {e}", fg="red")
        raise typer.Exit(code=1)

    try:
        result = client.add_bulk(payload)
        typer.secho("Bulk add successful!", fg="green")
        typer.echo(json.dumps(result, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("claim")
def claim(
    ttl: int = typer.Option(60, "--ttl", "-t", help="Seconds to hold the claim")
):
    """Claim the next available repository for processing (non‐blocking)."""
    try:
        claim = client.claim_repo(ttl=ttl)
        typer.echo(json.dumps(claim, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("claim-blocking")
def claim_blocking(
    timeout: float = typer.Option(
        config.get("QUEUE_TIMEOUT_SEC", 30.0),
        "--timeout", "-t",
        help="Max seconds to wait for an available repo",
    )
):
    """Block until a repository becomes available or timeout."""
    try:
        claim = client.claim_repo_blocking(timeout=timeout)
        typer.echo(json.dumps(claim, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("complete")
def complete(repo_url: str = typer.Argument(..., help="Repository URL to complete")):
    """Mark a claimed repository as complete and remove it."""
    try:
        resp = client.complete_repo(repo_url)
        typer.echo(json.dumps(resp, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("complete-bulk")
def complete_bulk(
    repo_urls: str = typer.Option(..., "--urls", "-u", help="JSON list of repository URLs")
):
    """Mark multiple claimed repositories as complete in one call."""
    try:
        urls = json.loads(repo_urls)
    except json.JSONDecodeError as e:
        typer.secho(f"Invalid JSON for repo URLs: {e}", fg="red")
        raise typer.Exit(code=1)

    try:
        resp = client.complete_bulk(urls)
        typer.echo(json.dumps(resp, indent=2))
    except Exception as e:
        _handle_error(e)


@app.command("delete")
def delete(
    repo_url: str = typer.Argument(..., help="Repository URL to delete"),
    remove_db: bool = typer.Option(
        True, "--remove-db/--keep-db", help="Also remove DB record (default: remove)"
    ),
):
    """Delete a repository from filesystem, optionally also from the database."""
    try:
        result = client.delete_repo(repo_url, remove_db=remove_db)
        typer.secho("Deleted successfully!", fg="green")
        typer.echo(json.dumps(result, indent=2))
    except Exception as e:
        _handle_error(e)


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


if __name__ == "__main__":
    app()
