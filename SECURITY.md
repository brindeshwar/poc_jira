# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue. Use GitHub's private
[security advisory form](../../security/advisories/new) or email the maintainer.

## Supported versions

Only the latest release on `main` receives fixes.

## Handling secrets

- `JIRA_API_TOKEN`, `GOOGLE_API_KEY` and `SERVICE_API_KEY` live only in `.env` (gitignored) or a
  deployment secret store. `.env.example` lists names only.
- `gitleaks` runs in pre-commit and CI.
- If a secret is committed, rotate it first (Atlassian: *Account → Security → API tokens*), then clean
  the history.

## Service-specific notes

- Set `SERVICE_API_KEY` whenever the service is reachable by anything other than the local hub. Callers
  send it as `X-API-Key`, and it's compared in constant time.
- The Jira API token acts with the full permissions of its user. Use a dedicated account limited to
  the target project where possible.
- No user or LLM-provided text is ever placed into JQL (see `AGENTS.md` §4 rule 4).
