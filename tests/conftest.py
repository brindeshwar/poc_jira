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
    """Just enough of Jira Cloud's REST v3 API, served through httpx.MockTransport."""

    def __init__(self) -> None:
        self.issues: dict[str, dict] = {}
        self.writes: list[tuple[str, str]] = []
        self.fail_create = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/rest/api/3")
        body = json.loads(request.content) if request.content else {}

        if request.method == "POST" and path == "/search/jql":
            label = re.search(r'labels = "([^"]+)"', body["jql"]).group(1)
            found = [
                {"key": k, "fields": {"summary": i["summary"]}}
                for k, i in self.issues.items()
                if label in i.get("labels", [])
            ]
            return httpx.Response(200, json={"issues": found[: body["maxResults"]]})

        if request.method == "GET" and path == "/user/search":
            query = request.url.params["query"].lower()
            return httpx.Response(200, json=[u for u in USERS if query in u["displayName"].lower()])

        if request.method == "POST" and path == "/issue":
            if self.fail_create:
                return httpx.Response(
                    400, json={"errorMessages": [], "errors": {"duedate": "Invalid date"}}
                )
            key = f"POC-{len(self.issues) + 1}"
            self.issues[key] = dict(body["fields"])
            self.writes.append(("create", key))
            return httpx.Response(201, json={"key": key})

        if request.method == "PUT" and path.startswith("/issue/"):
            key = path.rsplit("/", 1)[1]
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
    )
    return TaskSyncService(api, "POC")
