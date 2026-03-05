"""Shared helpers for command modules."""

from __future__ import annotations

from typing import Any, Optional

import typer

from plane_cli.config import Config
from plane_cli.output import print_error


def resolve_project(cfg: Config, project_flag: Optional[str]) -> str:
    """Resolve project ID from flag or config, or exit with error."""
    project_id = project_flag or cfg.project
    if not project_id:
        print_error(
            "config_error",
            "No project specified. Use --project or set defaults.project in config.",
        )
        raise typer.Exit(1)
    return project_id


def model_to_dict(obj: Any) -> dict:
    """Convert a Pydantic model or dict-like object to a plain dict."""
    return obj.model_dump() if hasattr(obj, "model_dump") else dict(obj)
