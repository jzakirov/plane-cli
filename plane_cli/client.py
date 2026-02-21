"""PlaneClient factory and retry logic."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

import typer
from plane.client.plane_client import PlaneClient
from plane.errors.errors import HttpError

from plane_cli.output import print_error

if TYPE_CHECKING:
    from plane_cli.config import Config

T = TypeVar("T")


def get_client(cfg: "Config") -> PlaneClient:
    """Build and return a PlaneClient, validating required credentials."""
    if not cfg.api_key:
        print_error(
            "auth_error",
            "No API key configured. Set PLANE_API_KEY, use --api-key, or run `plane config init`.",
        )
        raise typer.Exit(1)
    if not cfg.workspace_slug:
        print_error(
            "config_error",
            "No workspace slug configured. Set PLANE_WORKSPACE_SLUG, use --workspace, or run `plane config init`.",
        )
        raise typer.Exit(1)

    return PlaneClient(base_url=cfg.base_url, api_key=cfg.api_key)


def call_with_retry(fn: Callable[..., T], *args: Any, max_retries: int = 3, **kwargs: Any) -> T:
    """Call fn(*args, **kwargs) with retry on HTTP 429."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            if exc.status_code == 429:
                # Try to read Retry-After header
                retry_after = 5
                if hasattr(exc, "response") and exc.response is not None:
                    try:
                        retry_after = int(exc.response.headers.get("Retry-After", 5))
                    except (AttributeError, ValueError):
                        retry_after = 5

                if attempt < max_retries - 1:
                    time.sleep(retry_after)
                    continue
                else:
                    print_error(
                        "rate_limit",
                        f"Rate limit exceeded after {max_retries} attempts.",
                        status_code=429,
                    )
                    raise typer.Exit(2)
            else:
                _handle_http_error(exc)
                raise typer.Exit(1)

    # Should not reach here
    raise typer.Exit(1)


def _handle_http_error(exc: HttpError) -> None:
    """Translate an HttpError into a structured error output."""
    status = exc.status_code
    message = str(exc)

    if status == 401:
        error_type = "auth_error"
        message = "Authentication failed. Check your API key."
    elif status == 403:
        error_type = "forbidden"
        message = "Permission denied."
    elif status == 404:
        error_type = "not_found"
        message = f"Resource not found. {message}"
    elif status == 400:
        error_type = "validation_error"
    else:
        error_type = "api_error"

    print_error(error_type, message, status_code=status)
