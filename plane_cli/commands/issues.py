"""issues subcommand: list / get / create / update / delete + comment add/list."""

from __future__ import annotations

import html
import re
import sys
from typing import List, Optional

import typer
from plane.models.work_items import (
    CreateWorkItem,
    CreateWorkItemComment,
    PaginatedWorkItemResponse,
    UpdateWorkItem,
)

from plane_cli.client import get_client, call_with_retry
from plane_cli.commands import model_to_dict, resolve_project
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


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _build_list_params(
    per_page: int,
    cursor: Optional[str] = None,
    state: Optional[str] = None,
    assignee: Optional[str] = None,
    expand: Optional[str] = None,
    pql: Optional[str] = None,
) -> dict:
    """Build query params dict for work items list, bypassing SDK model (extra=ignore)."""
    params: dict = {"per_page": per_page}
    if cursor:
        params["cursor"] = cursor
    if state:
        params["state"] = state
    if assignee:
        params["assignee"] = assignee
    if expand:
        params["expand"] = expand
    if pql:
        params["pql"] = pql
    return params


def _matches_labels(issue: dict, wanted: set[str]) -> bool:
    """Return True if any of the issue's labels matches one of `wanted` by name or ID."""
    for lb in issue.get("labels") or []:
        if isinstance(lb, dict):
            if lb.get("name") in wanted or lb.get("id") in wanted:
                return True
        elif str(lb) in wanted:
            return True
    return False


def _resolve_label_uuids(
    client: object, workspace: str, project_id: str, requested: set[str]
) -> Optional[set[str]]:
    """Resolve label names or UUIDs to UUIDs.

    Returns the set of UUIDs if every requested entry resolved, or None if
    one or more names could not be resolved (e.g. the labels endpoint is
    not available on this project for this API key — a known Plane quirk
    for projects the user can read but isn't a direct member of).

    A None return tells the caller to fall back to client-side filtering.
    """
    uuids = {x for x in requested if _UUID_RE.match(x)}
    names = requested - uuids
    if not names:
        return uuids

    try:
        response = call_with_retry(client.labels.list, workspace, project_id)
        name_to_id = {lb.name: lb.id for lb in (response.results or []) if lb.id and lb.name}
    except Exception:
        return None

    for n in names:
        lid = name_to_id.get(n)
        if not lid:
            return None
        uuids.add(lid)
    return uuids


def _build_label_pql(uuids: set[str]) -> str:
    """Build a PQL clause that matches issues with any of the given label UUIDs."""
    quoted = ", ".join(f'"{u}"' for u in sorted(uuids))
    return f"label IN ({quoted})"


def _fetch_work_items(client: object, workspace: str, project_id: str, params: dict) -> object:
    """Call work_items._get directly and validate response."""
    raw = client.work_items._get(f"{workspace}/projects/{project_id}/work-items", params=params)
    return PaginatedWorkItemResponse.model_validate(raw)


@app.command("list")
def issues_list(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    state: Optional[str] = typer.Option(None, "--state", help="Filter by state ID"),
    assignee: Optional[str] = typer.Option(None, "--assignee", help="Filter by assignee ID"),
    label: Optional[List[str]] = typer.Option(
        None,
        "--label",
        "-l",
        help="Filter by label name or ID. Repeatable; matches issues that have ANY of the given labels.",
    ),
    page: int = typer.Option(1, "--page", help="Page number"),
    per_page: Optional[int] = typer.Option(None, "--per-page", help="Results per page"),
    all_pages: bool = typer.Option(False, "--all", help="Fetch all pages (cap: 1000)"),
) -> None:
    """List issues in a project."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)
    client = get_client(cfg)

    effective_per_page = per_page or cfg.per_page

    # Plane's REST API uses a PQL (Plane Query Language) expression for filtering,
    # passed as `?pql=...`. PQL only matches by UUID, so for `--label foo` we have
    # to resolve names to UUIDs first. If that resolution fails (typically because
    # the project labels endpoint isn't readable with this API key), we fall back
    # to fetching everything and filtering client-side against expanded labels.
    label_filter = set(label) if label else None
    pql: Optional[str] = None
    needs_client_filter = False
    expand: Optional[str] = None

    if label_filter:
        resolved = _resolve_label_uuids(client, cfg.workspace_slug, project_id, label_filter)
        if resolved is not None:
            pql = _build_label_pql(resolved)
        else:
            needs_client_filter = True
            expand = "labels"

    if all_pages:
        all_issues: list[dict] = []
        cursor: Optional[str] = None

        while True:
            params = _build_list_params(
                effective_per_page, cursor, state, assignee, expand=expand, pql=pql
            )
            response = _fetch_work_items(client, cfg.workspace_slug, project_id, params)
            batch = [model_to_dict(i) for i in (response.results or [])]
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
        cursor_str: Optional[str] = None
        if page > 1:
            offset = (page - 1) * effective_per_page
            cursor_str = f"{effective_per_page}:{offset}:0"

        params = _build_list_params(
            effective_per_page, cursor_str, state, assignee, expand=expand, pql=pql
        )
        response = _fetch_work_items(client, cfg.workspace_slug, project_id, params)
        issues = [model_to_dict(i) for i in (response.results or [])]

    if needs_client_filter and label_filter:
        issues = [i for i in issues if _matches_labels(i, label_filter)]

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
    project_id = resolve_project(cfg, project)
    client = get_client(cfg)

    issue = call_with_retry(client.work_items.retrieve, cfg.workspace_slug, project_id, issue_id)
    print_json(model_to_dict(issue))


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
    project_id = resolve_project(cfg, project)

    if priority is not None and priority not in _VALID_PRIORITIES:
        print_error(
            "validation_error",
            f"Invalid priority '{priority}'. Choose from: {', '.join(_VALID_PRIORITIES)}",
        )
        raise typer.Exit(1)

    data_kwargs: dict = {"name": title}

    if description is not None:
        desc_text = read_text_arg(description)
        data_kwargs["description_html"] = f"<p>{html.escape(desc_text)}</p>"
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
    print_json(model_to_dict(issue))


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
    project_id = resolve_project(cfg, project)

    data_kwargs: dict = {}

    if title is not None:
        data_kwargs["name"] = title
    if description is not None:
        desc_text = read_text_arg(description)
        data_kwargs["description_html"] = f"<p>{html.escape(desc_text)}</p>"
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
    print_json(model_to_dict(issue))


@app.command("delete")
def issues_delete(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="Issue ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete an issue."""
    cfg: Config = ctx.obj
    project_id = resolve_project(cfg, project)

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
    project_id = resolve_project(cfg, project)
    client = get_client(cfg)

    response = call_with_retry(
        client.work_items.comments.list, cfg.workspace_slug, project_id, issue_id
    )
    comments = [model_to_dict(c) for c in (response.results or [])]

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
    project_id = resolve_project(cfg, project)

    body_text = read_text_arg(body)
    comment_html = f"<p>{html.escape(body_text)}</p>"

    client = get_client(cfg)
    data = CreateWorkItemComment(comment_html=comment_html)
    comment = call_with_retry(
        client.work_items.comments.create,
        cfg.workspace_slug,
        project_id,
        issue_id,
        data,
    )
    print_json(model_to_dict(comment))
