"""labels subcommand: list / get / create / update / delete."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from plane.models.labels import CreateLabel, UpdateLabel

from plane_cli.client import get_client, call_with_retry
from plane_cli.commands import model_to_dict, resolve_project
from plane_cli.config import Config
from plane_cli.output import (
    print_json,
    print_error,
    build_labels_table,
    out_console,
)

app = typer.Typer(name="labels", help="Manage work item labels.", no_args_is_help=True)


@app.command("list")
def labels_list(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
) -> None:
    """List all labels in a project."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)
    client = get_client(cfg)

    response = call_with_retry(client.labels.list, cfg.workspace_slug, project_id)
    labels = [model_to_dict(lb) for lb in (response.results or [])]

    if cfg.pretty:
        table = build_labels_table(labels)
        out_console.print(table)
    else:
        print_json(labels)


@app.command("get")
def labels_get(
    ctx: typer.Context,
    label_id: str = typer.Argument(..., help="Label ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
) -> None:
    """Get a single label by ID."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)
    client = get_client(cfg)

    label = call_with_retry(client.labels.retrieve, cfg.workspace_slug, project_id, label_id)
    print_json(model_to_dict(label))


@app.command("create")
def labels_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Label name"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    color: Optional[str] = typer.Option(None, "--color", help="Hex color code"),
) -> None:
    """Create a new label."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)

    data_kwargs: dict = {"name": name}
    if color is not None:
        data_kwargs["color"] = color

    client = get_client(cfg)
    data = CreateLabel(**data_kwargs)
    label = call_with_retry(client.labels.create, cfg.workspace_slug, project_id, data)
    print_json(model_to_dict(label))


@app.command("update")
def labels_update(
    ctx: typer.Context,
    label_id: str = typer.Argument(..., help="Label ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    color: Optional[str] = typer.Option(None, "--color"),
) -> None:
    """Update a label."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)

    data_kwargs: dict = {}
    if name is not None:
        data_kwargs["name"] = name
    if color is not None:
        data_kwargs["color"] = color

    if not data_kwargs:
        print_error("validation_error", "No fields to update.")
        raise typer.Exit(1)

    client = get_client(cfg)
    data = UpdateLabel(**data_kwargs)
    label = call_with_retry(client.labels.update, cfg.workspace_slug, project_id, label_id, data)
    print_json(model_to_dict(label))


@app.command("delete")
def labels_delete(
    ctx: typer.Context,
    label_id: str = typer.Argument(..., help="Label ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a label."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)

    if not yes and not sys.stdin.isatty():
        print_error("validation_error", "Pass --yes for non-interactive deletion.")
        raise typer.Exit(1)
    if not yes:
        typer.confirm(f"Delete label {label_id}?", abort=True)

    client = get_client(cfg)
    call_with_retry(client.labels.delete, cfg.workspace_slug, project_id, label_id)
    print_json({"ok": True, "deleted": label_id})
