"""projects subcommand: list / get / create / update / delete."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from plane.models.projects import CreateProject, UpdateProject

from plane_cli.client import get_client, call_with_retry
from plane_cli.commands import model_to_dict
from plane_cli.config import Config
from plane_cli.output import (
    print_json,
    print_error,
    build_projects_table,
    out_console,
    read_text_arg,
)

app = typer.Typer(name="projects", help="Manage Plane projects.", no_args_is_help=True)


@app.command("list")
def projects_list(ctx: typer.Context) -> None:
    """List all projects in the workspace."""
    cfg: Config = ctx.obj
    client = get_client(cfg)

    response = call_with_retry(client.projects.list, cfg.workspace_slug)
    projects = [model_to_dict(p) for p in (response.results or [])]

    if cfg.pretty:
        table = build_projects_table(projects)
        out_console.print(table)
    else:
        print_json(projects)


@app.command("get")
def projects_get(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Get a single project by ID."""
    cfg: Config = ctx.obj
    client = get_client(cfg)

    project = call_with_retry(client.projects.retrieve, cfg.workspace_slug, project_id)
    print_json(model_to_dict(project))


@app.command("create")
def projects_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Project name"),
    identifier: Optional[str] = typer.Option(
        None, "--identifier", help="Short identifier (e.g. PROJ)"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description or '-' for stdin"
    ),
    network: Optional[str] = typer.Option(None, "--network", help="Network type: public or secret"),
) -> None:
    """Create a new project."""
    cfg: Config = ctx.obj
    client = get_client(cfg)

    desc_text: Optional[str] = None
    if description is not None:
        desc_text = read_text_arg(description)

    # network: 2 = public (secret/private = 0)
    network_int: Optional[int] = None
    if network is not None:
        if network.lower() == "public":
            network_int = 2
        elif network.lower() in ("secret", "private"):
            network_int = 0
        else:
            print_error(
                "validation_error", f"Invalid network value '{network}'. Use 'public' or 'secret'."
            )
            raise typer.Exit(1)

    data_kwargs: dict = {"name": name}
    if identifier is not None:
        data_kwargs["identifier"] = identifier
    if desc_text is not None:
        data_kwargs["description"] = desc_text
    if network_int is not None:
        data_kwargs["network"] = network_int

    data = CreateProject(**data_kwargs)
    project = call_with_retry(client.projects.create, cfg.workspace_slug, data)
    print_json(model_to_dict(project))


@app.command("update")
def projects_update(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description or '-' for stdin"
    ),
    network: Optional[str] = typer.Option(None, "--network", help="Network type: public or secret"),
) -> None:
    """Update a project."""
    cfg: Config = ctx.obj
    client = get_client(cfg)

    data_kwargs: dict = {}
    if name is not None:
        data_kwargs["name"] = name
    if description is not None:
        data_kwargs["description"] = read_text_arg(description)
    if network is not None:
        if network.lower() == "public":
            data_kwargs["network"] = 2
        elif network.lower() in ("secret", "private"):
            data_kwargs["network"] = 0
        else:
            print_error("validation_error", f"Invalid network value '{network}'.")
            raise typer.Exit(1)

    if not data_kwargs:
        print_error("validation_error", "No fields to update. Provide at least one option.")
        raise typer.Exit(1)

    data = UpdateProject(**data_kwargs)
    project = call_with_retry(client.projects.update, cfg.workspace_slug, project_id, data)
    print_json(model_to_dict(project))


@app.command("delete")
def projects_delete(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a project."""
    cfg: Config = ctx.obj

    if not yes and not sys.stdin.isatty():
        print_error("validation_error", "Pass --yes for non-interactive deletion.")
        raise typer.Exit(1)
    if not yes:
        typer.confirm(f"Delete project {project_id}?", abort=True)

    client = get_client(cfg)
    call_with_retry(client.projects.delete, cfg.workspace_slug, project_id)
    print_json({"ok": True, "deleted": project_id})
