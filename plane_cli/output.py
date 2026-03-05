"""Output helpers: JSON, errors, Rich tables."""

from __future__ import annotations

import html.parser
import json
import sys
from datetime import date, datetime
from typing import Any, Optional

from rich.console import Console
from rich.table import Table
from rich import box

# Use stderr for Rich pretty output so stdout stays clean for piping
err_console = Console(stderr=True)
out_console = Console()


# ---------------------------------------------------------------------------
# Core output primitives
# ---------------------------------------------------------------------------


def print_json(data: Any) -> None:
    """Print compact JSON to stdout."""
    print(json.dumps(data, default=_json_serial))


def print_error(
    error_type: str,
    message: str,
    status_code: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    """Print structured error JSON to stderr."""
    payload: dict[str, Any] = {"type": error_type, "message": message}
    if status_code is not None:
        payload["status_code"] = status_code
    if detail is not None:
        payload["detail"] = detail
    err_console.print_json(json.dumps({"error": payload}))


def _json_serial(obj: Any) -> Any:
    """JSON serializer for datetime/date objects."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


class _HTMLStripper(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def strip_description(raw: Optional[str]) -> str:
    """Convert Tiptap JSON / HTML / plain text to a plain string."""
    if not raw:
        return ""
    stripped = raw.strip()
    if not stripped:
        return ""

    # Tiptap JSON detection
    if stripped.startswith("{") and '"type"' in stripped and '"doc"' in stripped:
        try:
            doc = json.loads(stripped)
            return _walk_tiptap(doc)
        except json.JSONDecodeError:
            pass

    # HTML detection (crude but sufficient)
    if "<" in stripped and ">" in stripped:
        parser = _HTMLStripper()
        parser.feed(stripped)
        return parser.get_text()

    return stripped


def _walk_tiptap(node: Any) -> str:
    """Recursively extract text from a Tiptap doc node."""
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        parts = []
        for child in node.get("content", []):
            part = _walk_tiptap(child)
            if part:
                parts.append(part)
        return " ".join(parts)
    return ""


def read_text_arg(value: str) -> str:
    """If value is '-', read text from stdin; otherwise return value."""
    if value == "-":
        if sys.stdin.isatty():
            err_console.print("[dim]Reading from stdin (Ctrl+D to finish):[/dim]")
        return sys.stdin.read()
    return value


def truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len chars with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def relative_time(dt: Optional[datetime]) -> str:
    """Return a human-friendly relative timestamp."""
    if dt is None:
        return ""
    from datetime import timezone

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m}m ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h}h ago"
    d = seconds // 86400
    if d < 30:
        return f"{d}d ago"
    if d < 365:
        return f"{d // 30}mo ago"
    return f"{d // 365}y ago"


def _priority_style(priority: Optional[str]) -> str:
    styles = {
        "urgent": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "blue",
        "none": "dim",
    }
    return styles.get((priority or "none").lower(), "")


def _state_group_style(group: Optional[str]) -> str:
    styles = {
        "backlog": "dim",
        "unstarted": "white",
        "started": "cyan",
        "completed": "green",
        "cancelled": "red",
    }
    return styles.get((group or "").lower(), "")


def _color_swatch(hex_color: Optional[str]) -> str:
    """Return a Rich markup string with a colored square."""
    if not hex_color:
        return ""
    c = hex_color.strip().lstrip("#")
    if len(c) not in (3, 6):
        return hex_color
    full = c if len(c) == 6 else "".join(ch * 2 for ch in c)
    return f"[#{full}]■[/] #{full}"


# ---------------------------------------------------------------------------
# Rich table builders
# ---------------------------------------------------------------------------


def build_projects_table(projects: list[dict]) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Identifier", width=12)
    table.add_column("Name")
    table.add_column("Network", width=8)
    table.add_column("Members", width=7, justify="right")
    table.add_column("Created", width=12)

    for p in projects:
        pid = (p.get("id") or "")[:8]
        identifier = p.get("identifier") or ""
        name = p.get("name") or ""
        network_val = p.get("network")
        network = (
            "public"
            if network_val == 2
            else "secret"
            if network_val == 0
            else str(network_val or "")
        )
        members = str(p.get("total_members") or "")
        created = ""
        if p.get("created_at"):
            try:
                dt = datetime.fromisoformat(str(p["created_at"]).replace("Z", "+00:00"))
                created = relative_time(dt)
            except (ValueError, TypeError):
                created = str(p["created_at"])[:10]
        table.add_row(pid, identifier, name, network, members, created)

    return table


def build_issues_table(issues: list[dict]) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=6)
    table.add_column("Title", width=50)
    table.add_column("State", width=15)
    table.add_column("Priority", width=10)
    table.add_column("Assignees", width=20)
    table.add_column("Labels", width=20)
    table.add_column("Due Date", width=12)

    today = date.today()

    for issue in issues:
        seq = f"#{issue.get('sequence_id', '')}"
        title = truncate(issue.get("name") or "", 50)

        # State
        state = issue.get("state") or {}
        state_name = state.get("name") or "" if isinstance(state, dict) else str(state)
        state_group = state.get("group") or "" if isinstance(state, dict) else ""
        state_style = _state_group_style(state_group)
        state_cell = f"[{state_style}]{state_name}[/]" if state_style else state_name

        # Priority
        priority = issue.get("priority") or "none"
        pstyle = _priority_style(priority)
        priority_cell = f"[{pstyle}]{priority}[/]" if pstyle else priority

        # Assignees
        assignees_raw = issue.get("assignees") or []
        if assignees_raw and isinstance(assignees_raw[0], dict):
            assignees = ", ".join(
                a.get("display_name") or a.get("email") or str(a.get("id", ""))[:6]
                for a in assignees_raw
            )
        else:
            assignees = ", ".join(str(a)[:8] for a in assignees_raw)

        # Labels
        labels_raw = issue.get("labels") or []
        if labels_raw and isinstance(labels_raw[0], dict):
            labels = ", ".join(lb.get("name") or str(lb.get("id", ""))[:6] for lb in labels_raw)
        else:
            labels = ", ".join(str(lb)[:8] for lb in labels_raw)

        # Due date
        due_raw = issue.get("target_date")
        due_cell = ""
        if due_raw:
            try:
                due_date = date.fromisoformat(str(due_raw)[:10])
                due_str = str(due_raw)[:10]
                due_cell = f"[red]{due_str}[/]" if due_date < today else due_str
            except (ValueError, TypeError):
                due_cell = str(due_raw)[:10]

        table.add_row(seq, title, state_cell, priority_cell, assignees, labels, due_cell)

    return table


def build_states_table(states: list[dict]) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Name", width=20)
    table.add_column("Group", width=12)
    table.add_column("Color", width=15)
    table.add_column("Default", width=7, justify="center")

    for s in states:
        sid = (s.get("id") or "")[:8]
        name = s.get("name") or ""
        group = s.get("group") or ""
        gstyle = _state_group_style(group)
        group_cell = f"[{gstyle}]{group}[/]" if gstyle else group
        color_cell = _color_swatch(s.get("color"))
        default = "✓" if s.get("default") else ""
        table.add_row(sid, name, group_cell, color_cell, default)

    return table


def build_labels_table(labels: list[dict]) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Name", width=25)
    table.add_column("Color", width=15)

    for lb in labels:
        lid = (lb.get("id") or "")[:8]
        name = lb.get("name") or ""
        color_cell = _color_swatch(lb.get("color"))
        table.add_row(lid, name, color_cell)

    return table


def build_comments_table(comments: list[dict]) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Author", width=20)
    table.add_column("Body", width=80)
    table.add_column("Created", width=12)

    for c in comments:
        cid = (c.get("id") or "")[:8]
        actor = c.get("actor") or {}
        author = ""
        if isinstance(actor, dict):
            author = actor.get("display_name") or actor.get("email") or str(actor.get("id", ""))[:8]
        else:
            author = str(actor)[:8]

        body = truncate(
            strip_description(c.get("comment_html") or c.get("comment_stripped") or ""), 80
        )

        created = ""
        if c.get("created_at"):
            try:
                dt = datetime.fromisoformat(str(c["created_at"]).replace("Z", "+00:00"))
                created = relative_time(dt)
            except (ValueError, TypeError):
                created = str(c["created_at"])[:10]

        table.add_row(cid, author, body, created)

    return table
