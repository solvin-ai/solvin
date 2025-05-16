# modules/cli_agents.py

"""
CLI for managing conversational agents (list, message, run turns, etc)
"""

import typer
import json
import requests

from shared import client_agents

app = typer.Typer(
    help="Manage conversational agents (list, message, run turns, etc)"
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
    if any("repo_url" in a for a in agents):
        fields.append("repo_url")
    if any("created_at" in a for a in agents):
        fields.append("created_at")

    header = "  ".join(f.ljust(14) for f in fields)
    typer.echo(header)
    typer.echo("-" * (16 * len(fields)))
    for a in agents:
        row = "  ".join(str(a.get(f, ""))[:32].ljust(14) for f in fields)
        typer.echo(row)


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
def list_(
    repo_url:  str = typer.Option(..., "--repo-url", "-r", help="Repository URL to scope the query"),
):
    """List running agents."""
    agents = client_agents.list_running_agents(repo_url)
    echo_agent_table(agents)

@app.command("current")
def current(
    repo_url:  str = typer.Option(..., "--repo-url", "-r", help="Repository URL to scope the query"),
):
    """Show the current active agent."""
    print_json_result(client_agents.get_current_running_agent, repo_url)

@app.command("set-current")
def set_current(
    agent_role: str = typer.Argument(..., help="Agent role to set as current"),
    agent_id:   str = typer.Argument(..., help="Agent ID to set as current"),
    repo_url:   str = typer.Option(..., "--repo-url", "-r", help="Repository URL to scope the query"),
):
    """Set the current agent pointer."""
    print_json_result(
        client_agents.set_current_agent,
        agent_role,
        agent_id,
        repo_url
    )

@app.command("graph")
def graph(
    format:     str = typer.Option("json", "--format", "-f", 
                    help="Output format", show_choices=True, 
                    case_sensitive=False, 
                    # choices not supported by older typer; validate manually below
                ),
):
    """
    Retrieve the global agent spawn graph.
    format=json     → JSON list of edges [[p_role,p_id],[c_role,c_id],...]
    format=mermaid  → Mermaid sequenceDiagram DSL
    format=graphviz → Graphviz DOT source
    """
    fmt = format.lower()
    if fmt not in ("json", "mermaid", "graphviz"):
        typer.secho(f"ERROR: Unknown format '{format}'", fg="red", err=True)
        raise typer.Exit(1)

    try:
        resp = client_agents.get_agent_call_graph(fmt)
    except requests.exceptions.ConnectionError:
        typer.secho(
            "ERROR: Agents service is unreachable (connection refused). Is it running?",
            fg="red", err=True
        )
        raise typer.Exit(1)
    except requests.exceptions.HTTPError as e:
        typer.secho(f"ERROR: HTTP error from server: {e}", fg="red", err=True)
        try:
            err = e.response.json()
            typer.secho(json.dumps(err, indent=2), fg="red", err=True)
        except Exception:
            pass
        raise typer.Exit(2)
    except Exception as e:
        typer.secho(f"ERROR: Unexpected error: {e}", fg="red", err=True)
        raise typer.Exit(99)

    data = resp.get("data")
    if fmt == "json":
        typer.echo(json.dumps(data, indent=2))
    else:
        # mermaid or graphviz → raw string
        typer.echo(data)


#
# REGISTRY API
#

@app.command("agent_role-list")
def agent_role_list():
    """List agent role entries."""
    print_json_result(client_agents.list_registry)

@app.command("agent_role-get")
def agent_role_get(agent_role: str = typer.Argument(..., help="Agent role to get")):
    """Get a single agent role entry by name."""
    print_json_result(client_agents.get_agent_role, agent_role)

@app.command("agent_role-upsert")
def agent_role_upsert(json_str: str = typer.Argument(..., help="JSON string payload for upsert")):
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
def agent_role_delete(agent_role: str = typer.Argument(..., help="Agent role to delete")):
    """Delete an agent role by its name."""
    print_json_result(client_agents.delete_agent_role, agent_role)


#
# MESSAGE API
#

@app.command("messages-list")
def messages_list(
    agent_role: str = typer.Argument(..., help="Agent role"),
    agent_id:   str = typer.Argument(..., help="Agent ID"),
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
    agent_role: str = typer.Argument(..., help="Agent role"),
    agent_id:   str = typer.Argument(..., help="Agent ID"),
    role:       str = typer.Argument(..., help="Message role (e.g. user, assistant)"),
    content:    str = typer.Argument(..., help="Message content"),
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
    agent_role: str = typer.Argument(..., help="Agent role"),
    agent_id:   str = typer.Argument(..., help="Agent ID"),
    message_id: int = typer.Argument(..., help="Message ID"),
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
    agent_role: str = typer.Argument(..., help="Agent role"),
    agent_id:   str = typer.Argument(..., help="Agent ID"),
    message_id: int = typer.Argument(..., help="Message ID"),
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

@app.command("broadcast")
def broadcast(
    agent_roles:   str = typer.Argument(..., help="Comma-separated agent roles"),
    messages_json: str = typer.Argument(..., help="Message(s) JSON payload"),
    repo_url:      str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """
    Broadcast a message or messages to all agents in the specified roles.
    """
    roles = [r.strip() for r in agent_roles.split(",") if r.strip()]
    try:
        msgs = json.loads(messages_json)
    except Exception:
        msgs = messages_json
    print_json_result(
        client_agents.broadcast_to_agents,
        roles,
        msgs,
        repo_url=repo_url,
    )


#
# TURNS API
#

@app.command("turns-list")
def turns_list(
    agent_role: str = typer.Argument(..., help="Agent role"),
    agent_id:   str = typer.Argument(..., help="Agent ID"),
    limit:      int = typer.Option(50, help="Max turns to return"),
    offset:     int = typer.Option(0,  help="Pagination offset"),
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """List turns (tool invocation records) for the given agent."""
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
    agent_role: str = typer.Argument(..., help="Agent role"),
    agent_id:   str = typer.Argument(..., help="Agent ID"),
    turn:       int = typer.Argument(..., help="Turn number"),
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

@app.command("turns-metadata")
def turns_metadata(
    agent_role: str = typer.Argument(..., help="Agent role"),
    agent_id:   str = typer.Argument(..., help="Agent ID"),
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """Get the per-conversation metadata dict for the given agent."""
    print_json_result(
        client_agents.get_turns_metadata,
        agent_role,
        agent_id,
        repo_url,
    )


#
# RUN AGENT TASK
#

@app.command("run-agent-task")
def run_agent_task(
    agent_role:  str = typer.Argument(..., help="Agent role to invoke"),
    user_prompt: str = typer.Argument(..., help="User prompt to send to the agent"),
    repo_url:    str = typer.Option(..., "--repo-url", "-r", help="Repository URL"),
    agent_id:    str = typer.Option(None, "--agent-id", help="Optional existing agent_id to reuse"),
):
    """
    Find-or-create the specified agent (role + repo_url), inject the
    user prompt, and drive it to completion.
    """
    print_json_result(
        client_agents.run_agent_task,
        agent_role,
        repo_url,
        user_prompt,
        agent_id=agent_id,
    )


#
# SUBMIT PENDING MSGS TO LLM
#

@app.command("submit")
def submit(
    agent_role: str = typer.Argument(..., help="The agent's role"),
    agent_id:   str = typer.Argument(..., help="Agent ID"),
    repo_url:   str = typer.Option(None, "--repo-url", "-r", help="Repository URL"),
):
    """Submit pending messages to the LLM for the given agent."""
    print_json_result(
        client_agents.submit_to_llm,
        agent_role,
        agent_id,
        repo_url,
    )


if __name__ == "__main__":
    app()
