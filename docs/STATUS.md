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
| Docker image | ✅ builds in CI (`Docker build` job, required check) | 2026-10-13 |

## Current version

`0.2.0`, released 2026-10-13 (tag `v0.2.0`, GitHub release). Published at https://github.com/brindeshwar/poc_jira on 2026-10-13 (`main` = v0.1.0).

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
| 2026-10-13 | Protect `main`: PR + 5 required checks, linear history, rebase-only merges, 0 approvals | keeps `main` always green; linear history keeps the Conventional Commits readable; solo maintainer can't self-approve |

## Handoff log

### 2026-10-13: Claude (Opus 5.5) · dependency upgrades (Dependabot triage)
**Changed:** upgraded `google-genai` to 2.x. CI actions moved to their Node 24 majors.

**Verified:** release notes reviewed for every major bump; pytest (19); google-genai 2.29 API surface checked against every call we make (`generate_content`, `response_json_schema`).

**Next agent:** Dependabot's superseded PRs close automatically after merge. Future major bumps need the
same review (CI alone isn't enough where tests use fakes, e.g. Gemini).

### 2026-10-13: Claude (Opus 5.5) · v0.2.0 released, branch protection
**Changed:** merged the v2 PR (rebase), tagged `v0.1.0` (original POC) and `v0.2.0`, and published the
GitHub release. Protected `main`: PR required, 5 required checks (lint, tests 3.12/3.13, secret scan,
Docker build) that must be up to date, linear history, conversation resolution, no force-push or
deletion, enforced for admins. 0 approvals required (solo maintainer; GitHub forbids self-approval).
Rebase merge is the only merge method; merged branches are auto-deleted.

**Verified:** CI green on the PR and on `main` after merge; protection settings read back from the
GitHub API.

**Next agent:** unchanged. Live verification is blocked on a valid Gemini key (and Jira site / Slack
token rotation; see Known issues). All changes now go through a PR.

### 2026-10-13: Claude (Opus 5.5) · v2 rebuild + project infrastructure
**Changed:** removed the v1 code (`jira_helper.py`, `langchain_helper.py`, `requirements.txt`); rewrote the service into `src/jira_service` (label-based idempotent sync, REST v3,
API-key auth, dry run, 502 on extraction errors). Added tests with a fake Jira, and project
infrastructure (AGENTS/CLAUDE/docs, CI, pre-commit + gitleaks, Dependabot, templates, Dockerfile,
MIT license, CHANGELOG). Ran `git init`, published the repo to GitHub (public), and opened the v2 PR.

**Verified:** 19 tests; ruff; the service running locally answered `/health`; a dry run against the
configured Jira produced a clean per-item failure (site unavailable).

**Not verified:** real ticket creation, real Gemini extraction.

**Next agent:** Known issue #1 (new Jira site), then Backlog #1.
