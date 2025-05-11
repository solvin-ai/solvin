# modules/cli_agents.py

"""
CLI for managing conversational agents (add, remove, list, message, run turns, etc)
"""

import typer
import json
import sys
import requests            # still needed for catching HTTPError / ConnectionError
from shared import client_agents

app = typer.Typer(
    help="Manage conversational agents (add, remove, list, message, run turns, etc)"
)

def print_json_result(func, *args, **kwargs):
    """Wrap CLI command: print pretty JSON or error on failure."""
    try:
        result = func(*args, **kwargs)
        typer.echo(json.dumps(result, indent=2))
    except requests.exceptions.ConnectionError:
        typer.secho(
            "ERROR: Agents service is unreachable (connection refused). Is it running?",
            fg="red",
            err=True,
        )
        raise typer.Exit(1)
    except requests.exceptions.HTTPError as e:
        typer.secho(f"ERROR: HTTP error from server: {e}", fg="red", err=True)
        try:
            err_resp = e.response.json()
            typer.secho(json.dumps(err_resp, indent=2), fg="red", err=True)
        except Exception:
            pass
        raise typer.Exit(2)
    except Exception as e:
        typer.secho(f"ERROR: Unexpected error: {e}", fg="red", err=True)
        raise typer.Exit(99)

def echo_agent_table(agents):
    """Pretty print agent listing as a table."""
    if not agents:
        typer.echo("(no running agents)")
        return

    fields = ["agent_role", "agent_id"]
    if any("created_at" in a for a in agents):
        fields.append("created_at")

    typer.echo("  ".join(f"{f}".ljust(14) for f in fields))
    typer.echo("-" * 16 * len(fields))
    for a in agents:
        typer.echo("  ".join(str(a.get(f, ""))[:32].ljust(14) for f in fields))

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

#
# SERVICE HEALTH & STATUS
#

@app.command("health")
def health():
    """Check health of the agents service."""
    print_json_result(client_agents.health)

@app.command("ready")
def ready():
    """Check readiness of agents service."""
    print_json_result(client_agents.ready)

@app.command("status")
def status():
    """Show service status."""
    print_json_result(client_agents.status)

#
# RUNNING AGENTS
#

@app.command("list")
def list_():
    """List running agents."""
    try:
        agents = client_agents.list_running_agents()
        echo_agent_table(agents)
    except Exception as e:
        typer.secho(f"ERROR: {e}", fg="red", err=True)
        raise typer.Exit(4)

@app.command("add")
def add(agent_role: str):
    """Add an agent of the specified role."""
    print_json_result(client_agents.add_running_agent, agent_role)

@app.command("remove")
def remove(agent_role: str, agent_id: str):
    """Remove a running agent by role/id."""
    print_json_result(client_agents.remove_running_agent, agent_role, agent_id)

@app.command("current")
def current():
    """Show the current active agent."""
    print_json_result(client_agents.get_current_running_agent)

@app.command("set-current")
def set_current(agent_role: str, agent_id: str):
    """Set the current agent pointer."""
    print_json_result(client_agents.set_current_agent, agent_role, agent_id)

@app.command("clear-repo")
def clear_repo(
    repo_name: str = typer.Argument(
        ..., help="Name of the repository whose running agents should be cleared"
    )
):
    """
    Clear all running agents (and current pointer) for the specified repo.
    """
    print_json_result(client_agents.clear_repo, repo_name)

#
# REGISTRY API
#

@app.command("agent_role-list")
def agent_role_list():
    """List agent role entries."""
    print_json_result(client_agents.list_registry)

@app.command("agent_role-get")
def agent_role_get(agent_role: str):
    """Get a single agent role entry by name."""
    print_json_result(client_agents.get_agent_role, agent_role)

@app.command("agent_role-upsert")
def agent_role_upsert(json_str: str):
    """
    Add or update an agent role. Pass the payload as JSON string.
    """
    try:
        item = json.loads(json_str)
    except Exception as e:
        typer.secho(f"Could not parse JSON payload: {e}", fg="red", err=True)
        raise typer.Exit(3)
    print_json_result(client_agents.upsert_agent_role, **item)

@app.command("agent_role-delete")
def agent_role_delete(agent_role: str):
    """Delete an agent role by its name."""
    print_json_result(client_agents.delete_agent_role, agent_role)

#
# MESSAGE API
#

@app.command("messages-list")
def messages_list(
    agent_role: str,
    agent_id:   str,
    role:       str = typer.Option(None, help="Filter by message role"),
    turn_id:    int = typer.Option(None, help="Filter by turn number"),
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """List messages for the given agent."""
    print_json_result(
        client_agents.list_messages,
        agent_role,
        agent_id,
        repo_url,
        role,
        turn_id,
    )

@app.command("messages-add")
def messages_add(
    agent_role: str,
    agent_id:   str,
    role:       str,
    content:    str,
    meta_json:  str = typer.Option("{}", help="Extra JSON metadata"),
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """Add a message for the agent."""
    try:
        meta = json.loads(meta_json)
    except Exception as e:
        typer.secho(f"Could not parse meta JSON: {e}", fg="red", err=True)
        raise typer.Exit(3)

    print_json_result(
        client_agents.add_message,
        agent_role,
        agent_id,
        role,
        content,
        repo_url=repo_url,
        **meta,
    )

@app.command("messages-get")
def messages_get(
    agent_role: str,
    agent_id:   str,
    message_id: int,
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """Get a specific message by ID."""
    print_json_result(
        client_agents.get_message,
        agent_role,
        agent_id,
        message_id,
        repo_url,
    )

@app.command("messages-remove")
def messages_remove(
    agent_role: str,
    agent_id:   str,
    message_id: int,
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """Remove a specific message by ID."""
    print_json_result(
        client_agents.remove_message,
        agent_role,
        agent_id,
        message_id,
        repo_url,
    )

@app.command("messages-remove-all")
def messages_remove_all(
    agent_role: str,
    agent_id:   str,
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """Remove all messages for the given agent."""
    print_json_result(
        client_agents.remove_all_messages,
        agent_role,
        agent_id,
        repo_url,
    )

@app.command("messages-clear")
def messages_clear(
    repo_url:   str = typer.Option("*", "--repo-url", "-r", help="Repo URL or '*'"),
    agent_role: str = typer.Option("*", "--agent-role", "-R", help="Agent role or '*'"),
    agent_id:   str = typer.Option("*", "--agent-id", "-i", help="Agent ID or '*'"),
):
    """Clear stored turns & messages matching the given filters."""
    print_json_result(
        client_agents.clear_history,
        repo_url,
        agent_role,
        agent_id,
    )

#
# LLM AGENT OPS
#

@app.command("run-to-completion")
def run_to_completion(
    agent_role:  str = typer.Argument(..., help="The agent's role"),
    user_prompt: str = typer.Argument(..., help="User prompt to send to the agent"),
    agent_id:    str = typer.Option(None, help="Optional agent_id"),
    repo_url:    str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """
    Run to completion: inject a user prompt and drive the LLM workflow to completion.
    """
    print_json_result(
        client_agents.run_to_completion,
        agent_role,
        user_prompt,
        agent_id,
        repo_url,
    )

#
# BROADCAST
#

@app.command("broadcast")
def broadcast(agent_roles: str, message: str):
    """
    Broadcast a message to all agents in the specified roles.
    Comma‐separate multiple roles, e.g. "root,worker".
    """
    roles = [role.strip() for role in agent_roles.split(",") if role.strip()]
    print_json_result(client_agents.broadcast_to_agents, roles, message)

#
# TURNS API
#

@app.command("turns-list")
def turns_list(
    agent_role: str,
    agent_id:   str,
    limit:      int = typer.Option(50, help="Max turns to return"),
    offset:     int = typer.Option(0,  help="Pagination offset"),
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """List turns (tool‐invocation records) for the given agent."""
    print_json_result(
        client_agents.list_turns,
        agent_role,
        agent_id,
        repo_url,
        limit=limit,
        offset=offset,
    )

@app.command("turns-get")
def turns_get(
    agent_role: str,
    agent_id:   str,
    turn:       int,
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """Get a specific turn by its number."""
    print_json_result(
        client_agents.get_turn,
        agent_role,
        agent_id,
        repo_url,
        turn,
    )

if __name__ == "__main__":
    app()
