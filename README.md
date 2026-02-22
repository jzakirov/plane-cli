# plane-cli

Use [Plane.so](https://plane.so) without leaving the command line. Works great with AI agents.

> [!NOTE]
> This project was built with AI assistance (Claude). The code is functional and reviewed, but heads up if that matters to you.

```
plane projects list                         # list all projects in your workspace
plane issues list --pretty                  # view issues as a rich table
plane issues create --title "Fix login bug" # create an issue
plane issues list --all                     # fetch every page of issues
plane issues comment add <id> --body -      # pipe a comment body from stdin
```

## Installation

```bash
pip install plane-cli
```

Or with uv:

```bash
uv tool install plane-cli
```

## Configuration

Run the interactive setup wizard on first use:

```bash
plane config init
```

Config is stored in `~/.config/plane-cli/config.toml`:

```toml
[core]
api_key        = "plane_api_xxxxxxxx"
workspace_slug = "my-workspace"
base_url       = "https://api.plane.so"   # optional

[defaults]
project  = "uuid-of-default-project"      # optional
per_page = 20
```

### Environment variables

All config values can be overridden with environment variables — useful for CI or agent use:

| Environment variable   | Config key            |
|------------------------|-----------------------|
| `PLANE_API_KEY`        | `core.api_key`        |
| `PLANE_WORKSPACE_SLUG` | `core.workspace_slug` |
| `PLANE_BASE_URL`       | `core.base_url`       |
| `PLANE_PROJECT`        | `defaults.project`    |

CLI flags (`--api-key`, `--workspace`, `--base-url`, `--project`) override both.

### Get an API key

Go to **Plane → Settings → API Tokens** and create a token.

## Commands

### `config`

```
plane config init            # interactive setup wizard
plane config show            # print resolved config (api_key masked)
plane config show --reveal   # print full api_key
plane config set <key> <val> # set a single value, e.g. defaults.project <uuid>
```

### `projects`

```
plane projects list
plane projects get <project-id>
plane projects create --name NAME [--identifier ID] [--description TEXT] [--network public|secret]
plane projects update <project-id> [--name] [--description] [--network]
plane projects delete <project-id> [--yes]
```

### `issues`

```
plane issues list   [--project] [--state] [--priority] [--label] [--assignee]
                    [--page N] [--per-page N] [--all]
plane issues get    <issue-id>  [--project]
plane issues create --title TITLE [--project] [--description TEXT|-] [--state]
                    [--priority urgent|high|medium|low|none]
                    [--label ID]... [--assignee ID]... [--due-date YYYY-MM-DD]
plane issues update <issue-id>  [--project] [--title] [--description TEXT|-]
                    [--state] [--priority] [--label ID]... [--due-date]
plane issues delete <issue-id>  [--project] [--yes]

plane issues comment list <issue-id> [--project]
plane issues comment add  <issue-id> [--project] --body TEXT|-
```

### `states`

```
plane states list   [--project]
plane states get    <state-id>  [--project]
plane states create --name NAME --color HEX [--project]
                    [--group backlog|unstarted|started|completed|cancelled]
plane states update <state-id>  [--project] [--name] [--color] [--group]
plane states delete <state-id>  [--project] [--yes]
```

### `labels`

```
plane labels list   [--project]
plane labels get    <label-id>  [--project]
plane labels create --name NAME [--project] [--color HEX]
plane labels update <label-id>  [--project] [--name] [--color]
plane labels delete <label-id>  [--project] [--yes]
```

### `pages`

```
plane pages list    [--project]
plane pages get     <page-id>   [--project]
plane pages create  --name NAME [--project] [--description TEXT|-]
plane pages update  <page-id>   [--project] [--name] [--description TEXT|-]
plane pages delete  <page-id>   [--project] [--yes]
plane pages delete  <page-id>   [--project] --archive [--yes]
```

## Output

By default all commands print JSON to stdout, making them easy to pipe into `jq` or feed to an LLM:

```bash
plane issues list | jq '.[].name'
plane projects list | jq '.[] | {id, name: .identifier}'
```

Pass `--pretty` for Rich-rendered tables with color-coded priorities, state groups, and due-date highlighting:

```bash
plane issues list --pretty
plane states list --pretty
```

## Reading from stdin

Any `--description` or `--body` option accepts `-` to read from stdin:

```bash
plane issues create --title "Refactor auth" --description - <<'EOF'
Replace the JWT library with a simpler custom implementation.
Motivation: reduce bundle size and eliminate the CVE.
EOF

git diff HEAD~1 | plane issues comment add <id> --project <pid> --body -
```

## Pagination

```bash
plane issues list                # first page (default 20 per page)
plane issues list --per-page 50  # custom page size
plane issues list --page 3       # jump to a specific page
plane issues list --all          # fetch all pages, capped at 1000
```

## Agent use

Because output is plain JSON and the CLI is fully non-interactive by default (no prompts, no spinners on stdout), it works cleanly as a tool for LLM agents:

```bash
# safe to run in any non-TTY context
PLANE_API_KEY=... PLANE_WORKSPACE_SLUG=... plane issues list
# destructive commands require explicit --yes in non-TTY
plane issues delete <id> --yes
```

Errors are always JSON on stderr with a consistent shape:

```json
{ "error": { "type": "not_found", "message": "...", "status_code": 404 } }
```

Exit codes: `0` success · `1` error · `2` rate-limited (retry safe)

## License

MIT — see [LICENSE](LICENSE).
