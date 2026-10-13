# Architecture: Jira Task Service

## Context

The meeting hub sends structured action items to `POST /tasks`. The service can also extract them
from a raw transcript (`POST /tasks/from-transcript`). It writes to Jira Cloud through REST API v3.
The request and response contract is in the hub's
[`docs/INTEGRATION.md`](https://github.com/brindeshwar/poc_mcp/blob/main/docs/INTEGRATION.md).

## Components

```
HTTP ─► api.py ──(Depends)──► TaskSyncService (sync.py) ──► JiraAPI (jira_api.py) ──httpx──► Jira Cloud
            │
            └──(Depends)──► GeminiExtractor (extractor.py)  [only /tasks/from-transcript]
```

`get_sync_service` and `get_extractor` are cached dependency providers, so tests swap them with
`app.dependency_overrides`. `require_api_key` guards every write endpoint when `SERVICE_API_KEY` is set.

## Sync algorithm (per request)

```
label(item) = "ai-task-" + sha1(f"{meeting_id or ''}|{lowercase, whitespace-collapsed summary}")[:12]
group items by label                                   # duplicates in one request → one ticket

existing = search(project = KEY AND labels in (all labels))        # ONE call, injection-safe
for each distinct item:
    account = the one active human user matching `assignee`        # cached per distinct name
    fields  = summary, description (ADF; owner if unresolved, meeting title), duedate?, assignee?
    if label in existing:  update(key, fields minus {summary, project, issuetype})  → "updated"
    else:                  queue for creation                                       → "created"
bulk_create(queued, 50 per call)        # POST /issue/bulk; per-element failures → "failed"
dry run: same reads, zero writes        → "would_update" / "would_create"
```

**Call budget:** for N items with A distinct assignees, E of them existing: `1 search + A lookups +
ceil((N−E)/50) bulk creates + E updates`. v0.2 needed `N searches + N lookups + N creates`, so 10 new items
went from 30 calls to about 3.

**Resilience:** every call retries 429/502/503/504 up to 3 attempts. It honours `Retry-After` (capped
at 30s) and otherwise backs off 0.5s → 1s. A failing search fails every item with the reason; a failing
bulk call fails just that batch.

**Why scope the label by meeting?** The same summary in two meetings ("Follow up with client") is
usually different work. Scoping by `meeting_id` makes re-sending a meeting idempotent without ever
merging tickets across meetings. Without a `meeting_id` (raw transcript endpoint), identity is the
summary alone.

**Why not update the summary?** It defines the identity. Changing it would break the label mapping
for readers.

## Jira API usage

| Purpose | Call |
|---|---|
| Find existing tasks | `POST /rest/api/3/search/jql` `{jql: labels in (...), fields:["labels"]}` |
| Resolve assignee | `GET /rest/api/3/user/search?query=<name or email>&maxResults=5` |
| Create (bulk, ≤ 50) | `POST /rest/api/3/issue/bulk` `{issueUpdates:[{fields}]}` → `issues[]` + `errors[].failedElementNumber` |
| Update | `PUT /rest/api/3/issue/{key}` `{fields}` |

Auth: Basic (email + API token). Error messages are parsed from `errorMessages`, `errors{field:msg}`
and gateway-level `errorMessage`.

## Endpoints

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /health` | none | liveness |
| `POST /tasks` | API key (if set) | 1–50 items; used by the hub |
| `POST /tasks/from-transcript` | API key | `meeting_date` resolves "by Friday" etc.; 502 on extraction failure; 503 without `GOOGLE_API_KEY` |
| `POST /create-jira-tasks` | API key | v1 plain-text body; deprecated |

## Changes from v1

v1 matched existing tickets with a fuzzy `summary ~` search and updated the first hit, so it could
overwrite unrelated tickets. Updates cleared due dates and assignees that weren't mentioned, and LLM
errors became "no action items". It also built JQL from raw text and used the `jira` library's
search API, which Atlassian has since removed. See `CHANGELOG.md` 0.2.0.
