"""config subcommand: show / set / init."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

from plane_cli.config import (
    Config,
    CONFIG_PATH,
    config_as_dict,
    load_config,
    save_config,
    save_config_key,
)
from plane_cli.output import print_json, print_error, out_console

app = typer.Typer(name="config", help="Manage plane-cli configuration.", no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)


@app.command("show")
def config_show(
    ctx: typer.Context,
    reveal: bool = typer.Option(False, "--reveal", help="Show the full API key."),
) -> None:
    """Show the resolved configuration (masks api_key by default)."""
    cfg: Config = ctx.obj
    print_json(config_as_dict(cfg, reveal=reveal))


@app.command("set")
def config_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Dotted config key, e.g. defaults.project"),
    value: str = typer.Argument(..., help="Value to set"),
) -> None:
    """Write a config value. Example: plane config set defaults.project <UUID>"""
    try:
        save_config_key(key, value)
        print_json({"ok": True, "key": key, "value": value})
    except Exception as exc:
        print_error("config_error", f"Failed to write config: {exc}")
        raise typer.Exit(1)


@app.command("init")
def config_init(ctx: typer.Context) -> None:
    """Interactive first-run wizard (TTY only)."""
    if not sys.stdin.isatty():
        print_error("validation_error", "`plane config init` requires an interactive terminal.")
        raise typer.Exit(1)

    console.print("[bold]plane-cli setup wizard[/bold]")
    console.print(f"Config will be saved to: [dim]{CONFIG_PATH}[/dim]\n")

    cfg: Config = ctx.obj

    api_key = Prompt.ask(
        "API key",
        password=True,
        default=cfg.api_key or "",
    )
    workspace_slug = Prompt.ask(
        "Workspace slug",
        default=cfg.workspace_slug or "",
    )
    base_url = Prompt.ask(
        "Base URL",
        default=cfg.base_url,
    )

    if not api_key:
        print_error("validation_error", "API key is required.")
        raise typer.Exit(1)
    if not workspace_slug:
        print_error("validation_error", "Workspace slug is required.")
        raise typer.Exit(1)

    # Validate credentials by listing projects
    console.print("\nValidating credentials…")
    try:
        from plane.client.plane_client import PlaneClient

        client = PlaneClient(base_url=base_url, api_key=api_key)
        response = client.projects.list(workspace_slug)
        projects = response.results or []
        console.print(f"[green]✓[/green] Connected. Found {len(projects)} project(s).")
    except Exception as exc:
        print_error("auth_error", f"Could not connect: {exc}")
        raise typer.Exit(1)

    # Optionally set default project
    default_project: Optional[str] = None
    if projects:
        console.print("\nAvailable projects:")
        for i, p in enumerate(projects, 1):
            console.print(f"  {i}. [{p.identifier}] {p.name}  (id: {p.id})")
        choice = Prompt.ask(
            "Set a default project? Enter number or press Enter to skip",
            default="",
        )
        if choice.strip().isdigit():
            idx = int(choice.strip()) - 1
            if 0 <= idx < len(projects):
                default_project = projects[idx].id
                console.print(f"[green]✓[/green] Default project: {projects[idx].name}")

    # Build and save config
    new_cfg = load_config()
    new_cfg.api_key = api_key
    new_cfg.workspace_slug = workspace_slug
    new_cfg.base_url = base_url
    if default_project:
        new_cfg.project = default_project

    save_config(new_cfg)
    console.print(f"\n[green]✓[/green] Config saved to {CONFIG_PATH}")
    print_json(config_as_dict(new_cfg))
