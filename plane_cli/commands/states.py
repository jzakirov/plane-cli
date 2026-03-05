"""states subcommand: list / get / create / update / delete."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from plane.models.states import CreateState, UpdateState

from plane_cli.client import get_client, call_with_retry
from plane_cli.commands import model_to_dict, resolve_project
from plane_cli.config import Config
from plane_cli.output import (
    print_json,
    print_error,
    build_states_table,
    out_console,
)

app = typer.Typer(name="states", help="Manage work item states.", no_args_is_help=True)

_VALID_GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled")


@app.command("list")
def states_list(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
) -> None:
    """List all states in a project."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)
    client = get_client(cfg)

    response = call_with_retry(client.states.list, cfg.workspace_slug, project_id)
    states = [model_to_dict(s) for s in (response.results or [])]

    if cfg.pretty:
        table = build_states_table(states)
        out_console.print(table)
    else:
        print_json(states)


@app.command("get")
def states_get(
    ctx: typer.Context,
    state_id: str = typer.Argument(..., help="State ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
) -> None:
    """Get a single state by ID."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)
    client = get_client(cfg)

    state = call_with_retry(client.states.retrieve, cfg.workspace_slug, project_id, state_id)
    print_json(model_to_dict(state))


@app.command("create")
def states_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="State name"),
    color: str = typer.Option(..., "--color", help="Hex color code, e.g. #ff5733"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    group: Optional[str] = typer.Option(
        None, "--group", help=f"State group: {', '.join(_VALID_GROUPS)}"
    ),
) -> None:
    """Create a new state."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)

    if group is not None and group not in _VALID_GROUPS:
        print_error(
            "validation_error", f"Invalid group '{group}'. Choose from: {', '.join(_VALID_GROUPS)}"
        )
        raise typer.Exit(1)

    data_kwargs: dict = {"name": name, "color": color}
    if group is not None:
        data_kwargs["group"] = group

    client = get_client(cfg)
    data = CreateState(**data_kwargs)
    state = call_with_retry(client.states.create, cfg.workspace_slug, project_id, data)
    print_json(model_to_dict(state))


@app.command("update")
def states_update(
    ctx: typer.Context,
    state_id: str = typer.Argument(..., help="State ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    color: Optional[str] = typer.Option(None, "--color"),
    group: Optional[str] = typer.Option(None, "--group"),
) -> None:
    """Update a state."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)

    data_kwargs: dict = {}
    if name is not None:
        data_kwargs["name"] = name
    if color is not None:
        data_kwargs["color"] = color
    if group is not None:
        if group not in _VALID_GROUPS:
            print_error(
                "validation_error",
                f"Invalid group '{group}'. Choose from: {', '.join(_VALID_GROUPS)}",
            )
            raise typer.Exit(1)
        data_kwargs["group"] = group

    if not data_kwargs:
        print_error("validation_error", "No fields to update.")
        raise typer.Exit(1)

    client = get_client(cfg)
    data = UpdateState(**data_kwargs)
    state = call_with_retry(client.states.update, cfg.workspace_slug, project_id, state_id, data)
    print_json(model_to_dict(state))


@app.command("delete")
def states_delete(
    ctx: typer.Context,
    state_id: str = typer.Argument(..., help="State ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a state."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)

    if not yes and not sys.stdin.isatty():
        print_error("validation_error", "Pass --yes for non-interactive deletion.")
        raise typer.Exit(1)
    if not yes:
        typer.confirm(f"Delete state {state_id}?", abort=True)

    client = get_client(cfg)
    call_with_retry(client.states.delete, cfg.workspace_slug, project_id, state_id)
    print_json({"ok": True, "deleted": state_id})
