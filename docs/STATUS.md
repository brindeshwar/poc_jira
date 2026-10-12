# Project Status: Jira Task Service

> Living document. Update it at the end of every work session (`AGENTS.md` §6). Newest handoff on top.

## Health

| Check | State | As of |
|---|---|---|
| Tests (sync logic, API, auth, errors) | ✅ 19 passing | 2026-10-13 |
| Lint / format | ✅ clean | 2026-10-13 |
| Service starts; `/health` | ✅ verified | 2026-10-13 |
| Real Jira (dry run) | ⛔ Jira site returned 404 "Site temporarily unavailable" | 2026-10-13 |
| Real Gemini extraction | ⛔ Gemini key invalid | 2026-10-13 |
| Docker image | ⚠️ not built locally (Docker daemon not running); CI `docker` job builds it | 2026-10-13 |

## Current version

`0.2.0` (unreleased; branch `refactor/v2-connected-system`). Published at https://github.com/brindeshwar/poc_jira on 2026-10-13 (`main` = v0.1.0).

## Known issues / blockers

1. **Jira site unavailable.** The configured Atlassian site returns 404. Create a new free Jira
   Cloud site and API token and update `.env`.

## Backlog (prioritized)

| # | Item | Notes |
|---|---|---|
| 1 | Live dry run, then a real run, against a fresh Jira site | verify ADF, labels, user search |
| 2 | Configurable label prefix / extra labels / components | per-team conventions |
| 3 | Retry with backoff on Jira 429/5xx | respect `Retry-After` |
| 4 | Transition tickets to Done when the meeting marks an item complete | needs a "completed" signal from the hub |
| 5 | Async endpoints with `httpx.AsyncClient` | only if throughput matters |

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-10-13 | Exact label identity instead of fuzzy summary search | v1 could overwrite unrelated tickets |
| 2026-10-13 | Label scoped by `meeting_id` | re-sending is idempotent; never merges across meetings |
| 2026-10-13 | Partial updates only; never touch summary or labels | v1 wiped fields; summary is the identity |
| 2026-10-13 | Direct REST v3 via httpx instead of the `jira` library | old search endpoint removed by Atlassian; easy to fake in tests |
| 2026-10-13 | Per-item failures inside a 200 response | one bad item shouldn't block the others |
| 2026-10-13 | Keep the v1 `/create-jira-tasks` endpoint (deprecated) | backward compatibility for existing demos |

## Handoff log

### 2026-10-13: Claude (Opus 5.5) · v2 rebuild + project infrastructure
**Changed:** removed the v1 code (`jira_helper.py`, `langchain_helper.py`, `requirements.txt`); rewrote the service into `src/jira_service` (label-based idempotent sync, REST v3,
API-key auth, dry run, 502 on extraction errors). Added tests with a fake Jira, and project
infrastructure (AGENTS/CLAUDE/docs, CI, pre-commit + gitleaks, Dependabot, templates, Dockerfile,
MIT license, CHANGELOG). Ran `git init`, published the repo to GitHub (public), and opened the v2 PR.

**Verified:** 19 tests; ruff; the service running locally answered `/health`; a dry run against the
configured Jira produced a clean per-item failure (site unavailable).

**Not verified:** real ticket creation, real Gemini extraction.

**Next agent:** Known issue #1 (new Jira site), then Backlog #1.
