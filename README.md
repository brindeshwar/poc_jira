# Jira Task Service

[![CI](https://github.com/brindeshwar/poc_jira/actions/workflows/ci.yml/badge.svg)](https://github.com/brindeshwar/poc_jira/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Small FastAPI service that turns meeting action items into Jira Cloud tasks. It is one of three
connected projects:

```
Slack bot ──MCP──► Meeting hub (MCP server) ──HTTP──► Jira Task Service ──REST v3──► Jira Cloud
Streamlit ──MCP──┘
```

The [meeting hub](https://github.com/brindeshwar/poc_mcp) extracts action items when a meeting is
ingested and sends them here when someone asks for Jira tickets. The service can also be used on its
own with a raw transcript.

## What it guarantees

- **Idempotent.** Each action item gets a stable label (`ai-task-<hash of meeting id + summary>`).
  Re-sending the same meeting updates its own tickets instead of creating duplicates, and it can never
  overwrite an unrelated ticket (the v1 fuzzy summary search could).
- **Never clears data.** On update, only fields the meeting actually mentioned are changed. A missing
  due date or assignee leaves the existing value alone.
- **Safe assignee matching.** A user is assigned only when exactly one active human Jira account
  matches the name or email. Otherwise the task is left unassigned with a warning in the response.
- **Errors are reported.** An LLM failure is a `502`, not an empty "no action items" result. Jira
  failures fail just that item, and the response says why (Jira's own error message).
- **Dry run.** `"dry_run": true` shows what would be created or updated without writing anything.
- **Optional shared secret.** Set `SERVICE_API_KEY`, and callers must send it as `X-API-Key`.

## API

| Method | Path | Body | Purpose |
|---|---|---|---|
| `GET` | `/health` | | Liveness check |
| `POST` | `/tasks` | `{action_items: [...], meeting_id?, meeting_title?, dry_run?}` | Sync structured action items (used by the hub) |
| `POST` | `/tasks/from-transcript` | `{transcript, meeting_title?, meeting_date?, dry_run?}` | Extract with Gemini, then sync |
| `POST` | `/create-jira-tasks` | plain text | v1 endpoint, kept for compatibility |

An action item is `{summary, description?, assignee?, due_date? (YYYY-MM-DD)}`. Interactive docs are
at `http://127.0.0.1:8000/docs`.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
cp .env.example .env      # fill in Jira + Google credentials
uv sync
uv run jira-task-service  # http://127.0.0.1:8000
```

Try it without touching Jira:

```bash
curl -X POST localhost:8000/tasks -H "Content-Type: application/json" \
  -d '{"dry_run": true, "meeting_id": "demo", "action_items": [{"summary": "Write the rollback plan", "assignee": "Eve"}]}'
```

## Tests

```bash
uv run pytest       # uses an in-memory fake of the Jira REST API; no network or credentials
uv run ruff check .
```

## Layout

```
src/jira_service/
  api.py        FastAPI routes, API-key check, dependency wiring
  sync.py       create-or-update logic (labels, assignee resolution, dry run)
  jira_api.py   thin Jira Cloud REST v3 client (httpx) + ADF helper
  extractor.py  Gemini structured-output extraction
  models.py     request/response schemas
  config.py     settings from environment / .env
```

## Docker

```bash
docker build -t jira-task-service .
docker run --env-file .env -p 8000:8000 jira-task-service
```

## Documentation

| Doc | For |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Rules, invariants and commands for coding agents and contributors (`CLAUDE.md` imports it) |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Sync algorithm, Jira API usage, endpoints |
| [`docs/STATUS.md`](docs/STATUS.md) | Health, known issues, backlog, decisions, handoff log |
| [Integration contract](https://github.com/brindeshwar/poc_mcp/blob/main/docs/INTEGRATION.md) | The `/tasks` contract and `ActionItem` schema (lives in the hub repo) |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`SECURITY.md`](SECURITY.md) · [`CHANGELOG.md`](CHANGELOG.md) | Process |

## License

[MIT](LICENSE) © Brindeshwar Sharma
