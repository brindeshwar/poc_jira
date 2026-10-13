# Changelog

All notable changes to this project are documented here. Format:
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Changed
- Upgraded `google-genai` to 2.x (its breaking changes only affect the Interactions API, which isn't used).
- CI actions moved to their Node 24 versions (`checkout@v7`, `setup-uv@v7`, `setup-buildx-action@v4`,
  `build-push-action@v7`, `gitleaks-action@v3`). Node 20 was removed from GitHub-hosted runners.

## [0.2.0] - 2026-10-13

Rewrite as an idempotent service called by the ListenLoom meeting hub.

### Added
- `POST /tasks` syncs structured action items (used by the hub), with `meeting_id`,
  `meeting_title` and `dry_run`.
- `POST /tasks/from-transcript` takes JSON with `meeting_date` so relative deadlines resolve
  correctly.
- `GET /health`.
- Optional shared-secret auth (`SERVICE_API_KEY` / `X-API-Key`).
- Per-item `warnings` (e.g. an ambiguous assignee).
- Tests with an in-memory fake Jira, CI, pre-commit with gitleaks, Dependabot, Dockerfile, and
  contributor and agent documentation.

### Changed
- Existing tickets are found by an exact, meeting-scoped label (`ai-task-<hash>`) instead of a
  fuzzy summary search.
- Updates only change fields present in the request, and never the summary or labels.
- Assignees are set only when exactly one active human Jira user matches.
- Uses Jira Cloud REST API v3 directly (ADF descriptions, `/search/jql`) via httpx, replacing the
  `jira` library.
- `google-genai` structured output replaces LangChain.
- `/create-jira-tasks` (plain text) is kept but deprecated.

### Fixed
- Could overwrite an unrelated ticket whose summary loosely matched.
- Updating a ticket cleared its due date or assignee when the meeting didn't mention them.
- LLM failures were reported as "No actionable items found".
- JQL was built from unescaped text (quotes broke the query).
- The `/` route returned HTML as a JSON string.

## [0.1.0] - 2025-06

- Initial internship proof of concept.

[Unreleased]: https://github.com/brindeshwar/poc_jira/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/brindeshwar/poc_jira/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/brindeshwar/poc_jira/releases/tag/v0.1.0
