"""pages subcommand: list / get / create / update / delete (with API capability checks)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

import typer
from plane.errors.errors import HttpError
from plane.models.pages import CreatePage

from plane_cli.client import call_with_retry, get_client
from plane_cli.config import Config
from plane_cli.output import print_error, print_json, read_text_arg

app = typer.Typer(name="pages", help="Manage project pages.", no_args_is_help=True)


def _resolve_project(cfg: Config, project_flag: Optional[str]) -> str:
    project_id = project_flag or cfg.project
    if not project_id:
        print_error(
            "config_error",
            "No project specified. Use --project or set defaults.project in config.",
        )
        raise typer.Exit(1)
    return project_id


def _not_supported(op: str, status_code: int = 405) -> None:
    print_error(
        "not_supported",
        f"Pages '{op}' is not supported by this Plane server/plan (HTTP {status_code}).",
        status_code=status_code,
    )


@app.command("list")
def pages_list(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
) -> None:
    """List pages in a project (if API supports listing)."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)
    client = get_client(cfg)

    try:
        payload = client.pages._get(f"{cfg.workspace_slug}/projects/{project_id}/pages")
    except HttpError as exc:
        if exc.status_code in (404, 405):
            _not_supported("list", exc.status_code)
            raise typer.Exit(1)
        print_error("api_error", str(exc), status_code=exc.status_code)
        raise typer.Exit(1)

    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        print_json(payload["results"])
    elif isinstance(payload, list):
        print_json(payload)
    elif isinstance(payload, dict):
        print_json([payload])
    else:
        print_json([])


@app.command("get")
def pages_get(
    ctx: typer.Context,
    page_id: str = typer.Argument(..., help="Page ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
) -> None:
    """Get a single page by ID."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)
    client = get_client(cfg)

    page = call_with_retry(
        client.pages.retrieve_project_page,
        cfg.workspace_slug,
        project_id,
        page_id,
    )
    print_json(page.model_dump() if hasattr(page, "model_dump") else dict(page))


@app.command("create")
def pages_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Page name"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description HTML/text or '-' for stdin"
    ),
) -> None:
    """Create a page in a project."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)
    client = get_client(cfg)

    desc_text = "" if description is None else read_text_arg(description)
    data = CreatePage(name=name, description_html=f"<p>{desc_text}</p>")
    page = call_with_retry(
        client.pages.create_project_page,
        cfg.workspace_slug,
        project_id,
        data,
    )
    print_json(page.model_dump() if hasattr(page, "model_dump") else dict(page))


@app.command("update")
def pages_update(
    ctx: typer.Context,
    page_id: str = typer.Argument(..., help="Page ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New page name"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description HTML/text or '-' for stdin"
    ),
) -> None:
    """Update a project page (if API supports updates)."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)
    client = get_client(cfg)

    data: dict = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description_html"] = f"<p>{read_text_arg(description)}</p>"
    if not data:
        print_error("validation_error", "No fields to update. Provide --name and/or --description.")
        raise typer.Exit(1)

    try:
        payload = client.pages._patch(
            f"{cfg.workspace_slug}/projects/{project_id}/pages/{page_id}",
            data,
        )
    except HttpError as exc:
        if exc.status_code in (404, 405):
            _not_supported("update", exc.status_code)
            raise typer.Exit(1)
        print_error("api_error", str(exc), status_code=exc.status_code)
        raise typer.Exit(1)

    print_json(payload if isinstance(payload, dict) else {"ok": True, "updated": page_id})


@app.command("delete")
def pages_delete(
    ctx: typer.Context,
    page_id: str = typer.Argument(..., help="Page ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    archive: bool = typer.Option(False, "--archive", help="Archive instead of hard delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete or archive a page (if API supports it)."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)

    if not yes and not sys.stdin.isatty():
        print_error("validation_error", "Pass --yes for non-interactive deletion/archive.")
        raise typer.Exit(1)
    if not yes:
        action = "archive" if archive else "delete"
        typer.confirm(f"{action.title()} page {page_id}?", abort=True)

    client = get_client(cfg)

    try:
        if archive:
            archived_at = datetime.now(timezone.utc).isoformat()
            payload = client.pages._patch(
                f"{cfg.workspace_slug}/projects/{project_id}/pages/{page_id}",
                {"archived_at": archived_at},
            )
            print_json(
                payload
                if isinstance(payload, dict)
                else {"ok": True, "archived": page_id, "archived_at": archived_at}
            )
        else:
            client.pages._delete(f"{cfg.workspace_slug}/projects/{project_id}/pages/{page_id}")
            print_json({"ok": True, "deleted": page_id})
    except HttpError as exc:
        if exc.status_code in (404, 405):
            _not_supported("archive" if archive else "delete", exc.status_code)
            raise typer.Exit(1)
        print_error("api_error", str(exc), status_code=exc.status_code)
        raise typer.Exit(1)
