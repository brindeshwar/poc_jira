import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from jira_service.jira_api import BULK_LIMIT, JiraAPI, JiraAPIError, to_adf
from jira_service.models import ActionItem, SyncResponse, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

SOURCE_LABEL = "from-meeting"
CREATE_ONLY = frozenset({"summary", "project", "issuetype"})
DUPLICATE_WARNING = "Duplicate of an earlier item in this request; synced once."


def task_label(summary: str, meeting_id: str | None) -> str:
    """Stable label identifying 'this action item from this meeting'.

    Matching on an exact label (instead of a fuzzy summary search) means re-sending the same
    meeting updates its own tickets and can never overwrite an unrelated one."""
    key = f"{meeting_id or ''}|{' '.join(summary.lower().split())}"
    return f"ai-task-{hashlib.sha1(key.encode()).hexdigest()[:12]}"


@dataclass
class _Pending:
    """One distinct action item while a request is being synced."""

    item: ActionItem
    label: str
    indexes: list[int]  # positions in the request (more than one for duplicates)
    warnings: list[str] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)
    result: TaskResult | None = None


class TaskSyncService:
    def __init__(self, jira: JiraAPI, project_key: str, issue_type: str = "Task") -> None:
        self._jira = jira
        self._project_key = project_key
        self._issue_type = issue_type

    def sync(
        self,
        items: list[ActionItem],
        *,
        meeting_id: str | None = None,
        meeting_title: str | None = None,
        dry_run: bool = False,
    ) -> SyncResponse:
        """Sync all items with as few Jira calls as possible: one search covering every label, one
        user lookup per distinct assignee, one bulk create per 50 new items, and one update per
        existing item (Jira has no bulk partial update)."""
        pending = _group_duplicates(items, meeting_id)

        try:
            existing = self._find_by_labels({p.label for p in pending})
        except JiraAPIError as exc:
            logger.warning("Jira search failed: %s", exc)
            for p in pending:
                p.result = _failed(p.item, str(exc), p.warnings)
            return self._response(items, pending, dry_run)

        assignees: dict[str, tuple[str | None, str | None]] = {}
        to_create: list[_Pending] = []
        for p in pending:
            try:
                account_id = self._resolve_assignee(p.item.assignee, assignees, p.warnings)
                p.fields = self._fields(p.item, meeting_title, account_id)
                if p.label in existing:
                    key = existing[p.label]
                    if not dry_run:
                        # Summary is the identity of the task; project and issue type can't be
                        # edited. Fields the meeting didn't mention are left untouched (never
                        # cleared), because _fields only includes what the item provides.
                        update = {k: v for k, v in p.fields.items() if k not in CREATE_ONLY}
                        self._jira.update_issue(key, update)
                    p.result = self._result(p, "would_update" if dry_run else "updated", key)
                elif dry_run:
                    p.result = self._result(p, "would_create", None)
                else:
                    to_create.append(p)
            except JiraAPIError as exc:
                logger.warning("Failed to sync %r: %s", p.item.summary, exc)
                p.result = _failed(p.item, str(exc), p.warnings)

        self._bulk_create(to_create)
        return self._response(items, pending, dry_run)

    def _bulk_create(self, to_create: list[_Pending]) -> None:
        for start in range(0, len(to_create), BULK_LIMIT):
            batch = to_create[start : start + BULK_LIMIT]
            payloads = [p.fields | {"labels": [SOURCE_LABEL, p.label]} for p in batch]
            try:
                outcomes = self._jira.bulk_create(payloads)
            except JiraAPIError as exc:
                logger.warning("Bulk create failed: %s", exc)
                outcomes = [(None, str(exc))] * len(batch)
            for p, (key, error) in zip(batch, outcomes, strict=True):
                p.result = (
                    self._result(p, "created", key)
                    if key
                    else _failed(p.item, error or "Jira did not create it", p.warnings)
                )

    def _response(
        self, items: list[ActionItem], pending: list[_Pending], dry_run: bool
    ) -> SyncResponse:
        """One result per input item, in request order; duplicates share their ticket."""
        results: list[TaskResult | None] = [None] * len(items)
        for p in pending:
            assert p.result is not None
            first, *duplicates = p.indexes
            results[first] = p.result
            for i in duplicates:
                results[i] = p.result.model_copy(
                    update={"summary": items[i].summary, "warnings": [DUPLICATE_WARNING]}
                )
        final = [r for r in results if r is not None]
        return SyncResponse(message=_summarise(final, dry_run), results=final)

    def _result(self, p: _Pending, status: TaskStatus, key: str | None) -> TaskResult:
        return TaskResult(
            summary=p.item.summary,
            status=status,
            jira_key=key,
            jira_url=self._jira.browse_url(key) if key else None,
            warnings=p.warnings,
        )

    def _find_by_labels(self, labels: set[str]) -> dict[str, str]:
        """Map each label that already has an issue to that issue's key (oldest issue wins)."""
        if not labels:
            return {}
        # Both values are validated (project key pattern, hex labels), so this JQL is injection-safe.
        quoted = ", ".join(f'"{label}"' for label in sorted(labels))
        jql = f'project = "{self._project_key}" AND labels in ({quoted}) ORDER BY created ASC'
        issues = self._jira.search(jql, fields=["labels"], max_results=max(len(labels) * 2, 50))
        found: dict[str, str] = {}
        for issue in issues:
            for label in issue.get("fields", {}).get("labels", []):
                if label in labels:
                    found.setdefault(label, issue["key"])
        return found

    def _resolve_assignee(
        self,
        assignee: str | None,
        cache: dict[str, tuple[str | None, str | None]],
        warnings: list[str],
    ) -> str | None:
        """Resolve a spoken name/email to a Jira account. Lookups are cached per request."""
        if not assignee:
            return None
        key = assignee.strip().lower()
        if key not in cache:
            users = self._jira.find_users(assignee)
            if len(users) == 1:
                cache[key] = (users[0]["accountId"], None)
            elif not users:
                cache[key] = (None, f"No Jira user matches '{assignee}'; left unassigned.")
            else:
                names = ", ".join(u.get("displayName", "?") for u in users)
                cache[key] = (
                    None,
                    f"'{assignee}' matches several Jira users ({names}); left unassigned.",
                )
        account_id, warning = cache[key]
        if warning:
            warnings.append(warning)
        return account_id

    def _fields(
        self, item: ActionItem, meeting_title: str | None, account_id: str | None
    ) -> dict[str, Any]:
        body = item.description or item.summary
        if item.assignee and not account_id:
            body += f"\n\nOwner mentioned in the meeting: {item.assignee}"
        if meeting_title:
            body += f"\n\nCreated from meeting: {meeting_title}"
        fields: dict[str, Any] = {
            "project": {"key": self._project_key},
            "issuetype": {"name": self._issue_type},
            "summary": item.summary,
            "description": to_adf(body),
        }
        if item.due_date:
            fields["duedate"] = item.due_date
        if account_id:
            fields["assignee"] = {"accountId": account_id}
        return fields


def _group_duplicates(items: list[ActionItem], meeting_id: str | None) -> list[_Pending]:
    by_label: dict[str, _Pending] = {}
    for i, item in enumerate(items):
        label = task_label(item.summary, meeting_id)
        if label in by_label:
            by_label[label].indexes.append(i)
        else:
            by_label[label] = _Pending(item=item, label=label, indexes=[i])
    return list(by_label.values())


def _failed(item: ActionItem, message: str, warnings: list[str]) -> TaskResult:
    return TaskResult(summary=item.summary, status="failed", message=message, warnings=warnings)


def _summarise(results: list[TaskResult], dry_run: bool) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    order = ["would_create", "would_update"] if dry_run else ["created", "updated"]
    parts = [f"{counts[s]} {s.replace('_', ' ')}" for s in [*order, "failed"] if counts.get(s)]
    prefix = "Dry run: " if dry_run else ""
    return prefix + (", ".join(parts) if parts else "nothing to do") + "."
