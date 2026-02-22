"""issues subcommand: list / get / create / update / delete + comment add/list."""

from __future__ import annotations

import sys
from typing import List, Optional

import typer
from plane.models.work_items import (
    CreateWorkItem,
    CreateWorkItemComment,
    UpdateWorkItem,
)
from plane.models.query_params import WorkItemQueryParams

from plane_cli.client import get_client, call_with_retry
from plane_cli.config import Config
from plane_cli.output import (
    build_comments_table,
    build_issues_table,
    out_console,
    print_error,
    print_json,
    read_text_arg,
)

app = typer.Typer(name="issues", help="Manage issues (work items).", no_args_is_help=True)
comment_app = typer.Typer(name="comment", help="Manage issue comments.", no_args_is_help=True)
app.add_typer(comment_app)

_VALID_PRIORITIES = ("urgent", "high", "medium", "low", "none")
_MAX_ALL_PAGES = 1000


def _issue_to_dict(issue: object) -> dict:
    return issue.model_dump() if hasattr(issue, "model_dump") else dict(issue)


def _resolve_project(cfg: Config, project_flag: Optional[str]) -> str:
    project_id = project_flag or cfg.project
    if not project_id:
        print_error(
            "config_error",
            "No project specified. Use --project or set defaults.project in config.",
        )
        raise typer.Exit(1)
    return project_id


@app.command("list")
def issues_list(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    state: Optional[str] = typer.Option(None, "--state", help="Filter by state ID"),
    priority: Optional[str] = typer.Option(None, "--priority", help="Filter by priority"),
    label: Optional[List[str]] = typer.Option(
        None, "--label", help="Filter by label ID (repeatable)"
    ),
    assignee: Optional[List[str]] = typer.Option(
        None, "--assignee", help="Filter by assignee ID (repeatable)"
    ),
    page: int = typer.Option(1, "--page", help="Page number"),
    per_page: Optional[int] = typer.Option(None, "--per-page", help="Results per page"),
    all_pages: bool = typer.Option(False, "--all", help="Fetch all pages (cap: 1000)"),
) -> None:
    """List issues in a project."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)
    client = get_client(cfg)

    effective_per_page = per_page or cfg.per_page

    if all_pages:
        all_issues: list[dict] = []
        cursor: Optional[str] = None

        while True:
            params = WorkItemQueryParams(per_page=effective_per_page)
            if cursor:
                params.cursor = cursor

            response = call_with_retry(
                client.work_items.list, cfg.workspace_slug, project_id, params
            )
            batch = [_issue_to_dict(i) for i in (response.results or [])]
            all_issues.extend(batch)

            if len(all_issues) >= _MAX_ALL_PAGES:
                from plane_cli.output import err_console

                err_console.print(
                    f"[yellow]Warning: reached {_MAX_ALL_PAGES} issue limit; stopping pagination.[/yellow]"
                )
                all_issues = all_issues[:_MAX_ALL_PAGES]
                break

            if not response.next_page_results:
                break
            cursor = response.next_cursor

        issues = all_issues
    else:
        # Manual single-page fetch
        # cursor-based: build cursor from page number
        cursor_str: Optional[str] = None
        if page > 1:
            # Plane uses cursor format: "per_page:offset:0" style but the SDK
            # exposes next_cursor strings from responses. For manual page navigation
            # we use the offset pattern.
            offset = (page - 1) * effective_per_page
            cursor_str = f"{effective_per_page}:{offset}:0"

        params = WorkItemQueryParams(per_page=effective_per_page)
        if cursor_str:
            params.cursor = cursor_str

        response = call_with_retry(client.work_items.list, cfg.workspace_slug, project_id, params)
        issues = [_issue_to_dict(i) for i in (response.results or [])]

    if cfg.pretty:
        table = build_issues_table(issues)
        out_console.print(table)
    else:
        print_json(issues)


@app.command("get")
def issues_get(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="Issue ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
) -> None:
    """Get a single issue by ID."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)
    client = get_client(cfg)

    issue = call_with_retry(client.work_items.retrieve, cfg.workspace_slug, project_id, issue_id)
    print_json(_issue_to_dict(issue))


@app.command("create")
def issues_create(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t", help="Issue title"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description or '-' for stdin"
    ),
    state: Optional[str] = typer.Option(None, "--state", help="State ID"),
    priority: Optional[str] = typer.Option(
        None, "--priority", help=f"Priority: {', '.join(_VALID_PRIORITIES)}"
    ),
    label: Optional[List[str]] = typer.Option(None, "--label", help="Label ID (repeatable)"),
    assignee: Optional[List[str]] = typer.Option(
        None, "--assignee", help="Assignee ID (repeatable)"
    ),
    due_date: Optional[str] = typer.Option(None, "--due-date", help="Due date YYYY-MM-DD"),
) -> None:
    """Create a new issue."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)

    if priority is not None and priority not in _VALID_PRIORITIES:
        print_error(
            "validation_error",
            f"Invalid priority '{priority}'. Choose from: {', '.join(_VALID_PRIORITIES)}",
        )
        raise typer.Exit(1)

    data_kwargs: dict = {"name": title}

    if description is not None:
        desc_text = read_text_arg(description)
        data_kwargs["description_html"] = f"<p>{desc_text}</p>"
        data_kwargs["description_stripped"] = desc_text

    if state is not None:
        data_kwargs["state"] = state
    if priority is not None:
        data_kwargs["priority"] = priority
    if label:
        data_kwargs["labels"] = list(label)
    if assignee:
        data_kwargs["assignees"] = list(assignee)
    if due_date is not None:
        data_kwargs["target_date"] = due_date

    client = get_client(cfg)
    data = CreateWorkItem(**data_kwargs)
    issue = call_with_retry(client.work_items.create, cfg.workspace_slug, project_id, data)
    print_json(_issue_to_dict(issue))


@app.command("update")
def issues_update(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="Issue ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    title: Optional[str] = typer.Option(None, "--title", "-t"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description or '-' for stdin"
    ),
    state: Optional[str] = typer.Option(None, "--state", help="State ID"),
    priority: Optional[str] = typer.Option(None, "--priority"),
    label: Optional[List[str]] = typer.Option(None, "--label", help="Label ID (repeatable)"),
    due_date: Optional[str] = typer.Option(None, "--due-date", help="Due date YYYY-MM-DD"),
) -> None:
    """Update an issue."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)

    data_kwargs: dict = {}

    if title is not None:
        data_kwargs["name"] = title
    if description is not None:
        desc_text = read_text_arg(description)
        data_kwargs["description_html"] = f"<p>{desc_text}</p>"
        data_kwargs["description_stripped"] = desc_text
    if state is not None:
        data_kwargs["state"] = state
    if priority is not None:
        if priority not in _VALID_PRIORITIES:
            print_error(
                "validation_error",
                f"Invalid priority '{priority}'. Choose from: {', '.join(_VALID_PRIORITIES)}",
            )
            raise typer.Exit(1)
        data_kwargs["priority"] = priority
    if label:
        data_kwargs["labels"] = list(label)
    if due_date is not None:
        data_kwargs["target_date"] = due_date

    if not data_kwargs:
        print_error("validation_error", "No fields to update.")
        raise typer.Exit(1)

    client = get_client(cfg)
    data = UpdateWorkItem(**data_kwargs)
    issue = call_with_retry(
        client.work_items.update, cfg.workspace_slug, project_id, issue_id, data
    )
    print_json(_issue_to_dict(issue))


@app.command("delete")
def issues_delete(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="Issue ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete an issue."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)

    if not yes and not sys.stdin.isatty():
        print_error("validation_error", "Pass --yes for non-interactive deletion.")
        raise typer.Exit(1)
    if not yes:
        typer.confirm(f"Delete issue {issue_id}?", abort=True)

    client = get_client(cfg)
    call_with_retry(client.work_items.delete, cfg.workspace_slug, project_id, issue_id)
    print_json({"ok": True, "deleted": issue_id})


# ---------------------------------------------------------------------------
# comment sub-subcommand
# ---------------------------------------------------------------------------


@comment_app.command("list")
def comment_list(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="Issue ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
) -> None:
    """List comments on an issue."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)
    client = get_client(cfg)

    response = call_with_retry(
        client.work_items.comments.list, cfg.workspace_slug, project_id, issue_id
    )
    comments = [_issue_to_dict(c) for c in (response.results or [])]

    if cfg.pretty:
        table = build_comments_table(comments)
        out_console.print(table)
    else:
        print_json(comments)


@comment_app.command("add")
def comment_add(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="Issue ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    body: str = typer.Option(..., "--body", "-b", help="Comment body or '-' for stdin"),
) -> None:
    """Add a comment to an issue."""
    cfg: Config = ctx.obj
    project_id = _resolve_project(cfg, project)

    body_text = read_text_arg(body)
    comment_html = f"<p>{body_text}</p>"

    client = get_client(cfg)
    data = CreateWorkItemComment(comment_html=comment_html)
    comment = call_with_retry(
        client.work_items.comments.create,
        cfg.workspace_slug,
        project_id,
        issue_id,
        data,
    )
    print_json(_issue_to_dict(comment))
