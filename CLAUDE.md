# CLAUDE.md

@AGENTS.md

## Claude Code specifics

- `AGENTS.md` (imported above) holds the shared rules. Add anything that applies to every agent
  there; this file is only for Claude-specific workflow.
- The hub repo is at `../../poc_mcp`. Its `docs/INTEGRATION.md` defines the `/tasks` contract.
  Use plan mode for any change to request or response models.
- When exercising the running service against a real Jira, always send `"dry_run": true` unless the
  user explicitly asked to create tickets.
- Before finishing: `uv run ruff format . && uv run ruff check . && uv run pytest`, report the real
  result, then add a Handoff entry to `docs/STATUS.md`.
