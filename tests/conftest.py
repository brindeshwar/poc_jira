import json
import re
from datetime import date

import httpx
import pytest

from jira_service.jira_api import JiraAPI
from jira_service.models import ActionItem
from jira_service.sync import TaskSyncService

USERS = [
    {
        "accountId": "acc-eve",
        "displayName": "Eve Adams",
        "accountType": "atlassian",
        "active": True,
    },
    {
        "accountId": "acc-bob1",
        "displayName": "Bob Stone",
        "accountType": "atlassian",
        "active": True,
    },
    {"accountId": "acc-bob2", "displayName": "Bob Lee", "accountType": "atlassian", "active": True},
    {"accountId": "bot", "displayName": "Eve Bot", "accountType": "app", "active": True},
]


class FakeJira:
    """Just enough of Jira Cloud's REST v3 API, served through httpx.MockTransport.

    Mirrors real behaviour that matters to us: `labels in (...)` search, bulk create with
    per-element failures, rejection of non-editable fields on update, and 429 rate limiting."""

    NOT_EDITABLE = {"project", "issuetype"}

    def __init__(self) -> None:
        self.issues: dict[str, dict] = {}
        self.writes: list[tuple[str, str]] = []
        self.calls: list[tuple[str, str]] = []
        self.fail_summaries: set[str] = set()  # bulk elements with these summaries fail
        self.throttle_next = 0  # respond 429 to the next N requests
        self.sleeps: list[float] = []  # retry delays the client asked for

    def count(self, method: str, path: str) -> int:
        return sum(1 for c in self.calls if c == (method, path))

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/rest/api/3")
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, path))

        if self.throttle_next:
            self.throttle_next -= 1
            return httpx.Response(
                429, headers={"Retry-After": "2"}, json={"errorMessages": ["Rate limited"]}
            )

        if request.method == "POST" and path == "/search/jql":
            wanted = set(re.findall(r'"(ai-task-[0-9a-f]+)"', body["jql"]))
            found = [
                {"key": k, "fields": {"labels": i.get("labels", [])}}
                for k, i in self.issues.items()
                if wanted & set(i.get("labels", []))
            ]
            return httpx.Response(200, json={"issues": found[: body["maxResults"]]})

        if request.method == "GET" and path == "/user/search":
            query = request.url.params["query"].lower()
            return httpx.Response(200, json=[u for u in USERS if query in u["displayName"].lower()])

        if request.method == "POST" and path == "/issue/bulk":
            issues, errors = [], []
            for n, update in enumerate(body["issueUpdates"]):
                fields = update["fields"]
                if fields["summary"] in self.fail_summaries:
                    errors.append(
                        {
                            "status": 400,
                            "failedElementNumber": n,
                            "elementErrors": {
                                "errorMessages": [],
                                "errors": {"duedate": "Invalid date"},
                            },
                        }
                    )
                    continue
                key = f"POC-{len(self.issues) + 1}"
                self.issues[key] = dict(fields)
                self.writes.append(("create", key))
                issues.append({"id": str(len(self.issues)), "key": key})
            return httpx.Response(
                400 if errors and not issues else 201, json={"issues": issues, "errors": errors}
            )

        if request.method == "PUT" and path.startswith("/issue/"):
            key = path.rsplit("/", 1)[1]
            bad = self.NOT_EDITABLE & set(body["fields"])
            if bad:
                return httpx.Response(
                    400,
                    json={"errorMessages": [], "errors": {f: "Field cannot be set." for f in bad}},
                )
            self.issues[key].update(body["fields"])
            self.writes.append(("update", key))
            return httpx.Response(204)

        return httpx.Response(404, json={"errorMessages": [f"Unhandled {request.method} {path}"]})


class FakeExtractor:
    def __init__(self, items: list[ActionItem]) -> None:
        self.items = items
        self.dates: list[date] = []

    def extract(self, transcript: str, meeting_date: date) -> list[ActionItem]:
        self.dates.append(meeting_date)
        return self.items


@pytest.fixture
def fake_jira() -> FakeJira:
    return FakeJira()


@pytest.fixture
def sync_service(fake_jira: FakeJira) -> TaskSyncService:
    api = JiraAPI(
        "https://example.atlassian.net",
        "me@example.com",
        "token",
        transport=httpx.MockTransport(fake_jira.handler),
        sleep=fake_jira.sleeps.append,
    )
    return TaskSyncService(api, "POC")
