# AGENTS.md: Jira Task Service

Instructions for **any** coding agent (Claude Code, Codex, Cursor, Copilot, Gemini CLI, Aider, …) and
for humans. This file is the source of truth for working in this repo. `CLAUDE.md` only adds to it.

## 1. What this repo is

A small FastAPI service that turns meeting action items into Jira Cloud tasks **idempotently**. It is
one of three repos:

```
poc_slack ──MCP──► poc_mcp (meeting hub) ──HTTP POST /tasks──► poc_jira (THIS REPO) ──REST v3──► Jira Cloud
```

| Repo | Local path | Role |
|---|---|---|
| `poc_jira` | `../poc_jira/jira_task_creator` | Jira Task Service (this repo): github.com/brindeshwar/poc_jira |
| `poc_mcp` | `../../poc_mcp` | MCP hub; the main caller. **Owns the integration contract:** `../../poc_mcp/docs/INTEGRATION.md` |
| `poc_slack` | `../../poc_slack` | Slack bot (reaches this service only through the hub) |

Read next: `docs/ARCHITECTURE.md` (sync algorithm, Jira API usage), `docs/STATUS.md` (state, backlog,
**handoff log**), and the hub's `INTEGRATION.md` (the `/tasks` contract and `ActionItem` schema).

## 2. Commands

| Task | Command |
|---|---|
| Install | `uv sync` |
| Run | `uv run jira-task-service` (http://127.0.0.1:8000, docs at `/docs`) |
| Tests | `uv run pytest` |
| Lint / format | `uv run ruff check .` / `uv run ruff format .` |
| Pre-commit | `uv run pre-commit run --all-files` |
| Docker | `docker build -t jira-task-service .` |

**Definition of done:** `uv run ruff format . && uv run ruff check . && uv run pytest` passes.

## 3. Repo map

```
src/jira_service/
  api.py        FastAPI routes, X-API-Key check, dependency providers (get_sync_service, get_extractor)
  sync.py       TaskSyncService: label lookup → create or partial update; assignee resolution; dry run
  jira_api.py   JiraAPI: thin httpx client for Jira Cloud REST v3 + to_adf() + error-message parsing
  extractor.py  GeminiExtractor: transcript → ActionItem[] (structured output), date-aware prompt
  models.py     ActionItem (shared contract), SyncRequest, TranscriptRequest, TaskResult, SyncResponse
  config.py     Settings: the ONLY place env vars are read; project key is pattern-validated
tests/          conftest.py (FakeJira over httpx.MockTransport, FakeExtractor); test_sync.py, test_api.py
main.py         compatibility shim so `uvicorn main:app` still works
```

## 4. Rules (invariants, do not break)

1. **Idempotency.** An action item's identity is the label `ai-task-<sha1(meeting_id|normalized
   summary)[:12]>`. Look up by exact label, never by fuzzy summary search. (v1 used `summary ~` and
   could overwrite unrelated tickets.)
2. **Never clear fields.** Updates only send fields the request provides. A missing due date or
   assignee leaves Jira's value alone. Summary and labels are never changed on update.
3. **Assign only on an unambiguous match:** exactly one active `atlassian` (human) account.
   Otherwise leave it unassigned and add a `warnings` entry.
4. **JQL safety.** Only validated values go into JQL (project key matches `^[A-Z][A-Z0-9_]{1,19}$`,
   and the label is hex). Never interpolate user or LLM text into JQL.
5. **Errors are visible.** An extraction failure is a `502`, never an empty result. A Jira failure fails
   just that item (`status: failed`, with Jira's message). The request still returns 200 with
   per-item results.
6. **Contract.** `ActionItem`, `SyncRequest` and `SyncResponse` are defined in the hub's
   `INTEGRATION.md` and mirrored in `poc_mcp/src/meeting_hub/models.py`. Change them only together
   with that doc, the hub, and a BREAKING changelog entry.
7. **Jira API v3** uses Atlassian Document Format for descriptions (`to_adf`) and
   `POST /search/jql` for search (the old `/search` endpoint is removed in Jira Cloud).

**Tests:** no network. Use `FakeJira` (`tests/conftest.py`), which implements the subset of Jira
REST v3 we call. Extend it when you call a new endpoint. Bug fixes include a regression test.
Override FastAPI dependencies via `app.dependency_overrides`.

**Security:** never commit `.env`. Read config only via `Settings`. `SERVICE_API_KEY` comparison uses
`secrets.compare_digest`. `gitleaks` runs in pre-commit and CI.

**Style:** Python 3.12+, type hints, Pydantic v2, ruff (line length 100), `logging` not `print`.
Endpoints are sync `def` because `JiraAPI` and the Gemini call are sync. FastAPI runs them in a
threadpool.

## 5. Workflow

**`main` is protected:** every change goes through a PR with green, up-to-date CI (lint, tests 3.12/3.13,
secret scan, Docker build) and is rebase-merged. Never push to `main` directly or force-push.

Branches `feat/…`, `fix/…`, `docs/…`, `chore/…`, `refactor/…`, `ci/…`. Conventional Commits. PRs use the
template and need green CI. User-visible changes go under `[Unreleased]` in `CHANGELOG.md`.

## 6. Handoff protocol (multi-agent)

1. **Start:** read `docs/STATUS.md`.
2. **Decisions:** record notable choices in its Decision log.
3. **End:** add a dated Handoff entry on top (changed / verified how / unfinished / next) and update
   Health and Backlog.

## 7. Gotchas

- The repo lives in `poc_jira/jira_task_creator`. The parent folder `poc_jira/` is not part of
  the repo.
- Never run the service against a real Jira in tests or demos without `"dry_run": true` unless you
  intend to create tickets.
