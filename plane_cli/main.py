"""plane-cli root application."""

from __future__ import annotations

from typing import Optional

import typer

from plane_cli.config import load_config
from plane_cli.commands import config_cmd, issues, labels, pages, projects, states

app = typer.Typer(
    name="plane",
    help="[bold]plane-cli[/bold] — Plane.so from the command line.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Register sub-apps
app.add_typer(config_cmd.app, name="config")
app.add_typer(projects.app, name="projects")
app.add_typer(issues.app, name="issues")
app.add_typer(states.app, name="states")
app.add_typer(labels.app, name="labels")
app.add_typer(pages.app, name="pages")


@app.callback()
def main(
    ctx: typer.Context,
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar="PLANE_API_KEY",
        help="Plane API key (overrides config)",
        show_envvar=True,
    ),
    workspace: Optional[str] = typer.Option(
        None,
        "--workspace",
        envvar="PLANE_WORKSPACE_SLUG",
        help="Workspace slug (overrides config)",
        show_envvar=True,
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url",
        envvar="PLANE_BASE_URL",
        help="API base URL (overrides config)",
        show_envvar=True,
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        envvar="PLANE_PROJECT",
        help="Default project ID (overrides config)",
        show_envvar=True,
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Render Rich tables instead of JSON output",
    ),
) -> None:
    """plane-cli: interact with Plane.so without leaving your terminal."""
    ctx.ensure_object(dict)
    cfg = load_config(
        api_key_flag=api_key,
        workspace_flag=workspace,
        base_url_flag=base_url,
        project_flag=project,
    )
    cfg.pretty = pretty
    ctx.obj = cfg
