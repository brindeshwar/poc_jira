import hashlib
import logging
from typing import Any

from jira_service.jira_api import JiraAPI, JiraAPIError, to_adf
from jira_service.models import ActionItem, SyncResponse, TaskResult

logger = logging.getLogger(__name__)

SOURCE_LABEL = "from-meeting"


def task_label(summary: str, meeting_id: str | None) -> str:
    """Stable label identifying 'this action item from this meeting'.

    Matching on an exact label (instead of a fuzzy summary search) means re-sending the same
    meeting updates its own tickets and can never overwrite an unrelated one."""
    key = f"{meeting_id or ''}|{' '.join(summary.lower().split())}"
    return f"ai-task-{hashlib.sha1(key.encode()).hexdigest()[:12]}"


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
        results = [self._sync_one(item, meeting_id, meeting_title, dry_run) for item in items]
        return SyncResponse(message=_summarise(results, dry_run), results=results)

    def _sync_one(
        self,
        item: ActionItem,
        meeting_id: str | None,
        meeting_title: str | None,
        dry_run: bool,
    ) -> TaskResult:
        label = task_label(item.summary, meeting_id)
        warnings: list[str] = []
        try:
            existing = self._find_by_label(label)
            account_id = self._resolve_assignee(item.assignee, warnings)
            fields = self._fields(item, meeting_title, account_id)

            if existing:
                key = existing["key"]
                if not dry_run:
                    # Summary is the identity of the task, and labels are ours; update the rest.
                    # Fields the meeting didn't mention are left untouched (never cleared).
                    update = {k: v for k, v in fields.items() if k not in ("summary", "labels")}
                    self._jira.update_issue(key, update)
                status = "would_update" if dry_run else "updated"
            else:
                key = (
                    None
                    if dry_run
                    else self._jira.create_issue(fields | {"labels": [SOURCE_LABEL, label]})
                )
                status = "would_create" if dry_run else "created"
        except JiraAPIError as exc:
            logger.warning("Failed to sync %r: %s", item.summary, exc)
            return TaskResult(
                summary=item.summary, status="failed", message=str(exc), warnings=warnings
            )

        return TaskResult(
            summary=item.summary,
            status=status,
            jira_key=key,
            jira_url=self._jira.browse_url(key) if key else None,
            warnings=warnings,
        )

    def _find_by_label(self, label: str) -> dict[str, Any] | None:
        # Both values are validated (project key pattern, hex label), so this JQL is injection-safe.
        jql = f'project = "{self._project_key}" AND labels = "{label}" ORDER BY created ASC'
        issues = self._jira.search(jql, fields=["summary"], max_results=1)
        return issues[0] if issues else None

    def _resolve_assignee(self, assignee: str | None, warnings: list[str]) -> str | None:
        if not assignee:
            return None
        users = self._jira.find_users(assignee)
        if len(users) == 1:
            return users[0]["accountId"]
        if not users:
            warnings.append(f"No Jira user matches '{assignee}'; left unassigned.")
        else:
            names = ", ".join(u.get("displayName", "?") for u in users)
            warnings.append(f"'{assignee}' matches several Jira users ({names}); left unassigned.")
        return None

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


def _summarise(results: list[TaskResult], dry_run: bool) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    order = ["would_create", "would_update"] if dry_run else ["created", "updated"]
    parts = [f"{counts[s]} {s.replace('_', ' ')}" for s in [*order, "failed"] if counts.get(s)]
    prefix = "Dry run: " if dry_run else ""
    return prefix + (", ".join(parts) if parts else "nothing to do") + "."
