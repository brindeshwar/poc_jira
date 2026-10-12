from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from jira_service import api
from jira_service.config import Settings
from jira_service.extractor import ExtractionError
from jira_service.models import ActionItem
from tests.conftest import FakeExtractor


def make_settings(**overrides) -> Settings:
    values = {
        "jira_url": "https://example.atlassian.net",
        "jira_email": "me@example.com",
        "jira_api_token": "token",
        "jira_project_key": "POC",
    } | overrides
    return Settings(_env_file=None, **values)


@pytest.fixture
def extractor() -> FakeExtractor:
    return FakeExtractor([ActionItem(summary="Write the rollback plan")])


@pytest.fixture
def client(monkeypatch, sync_service, extractor):
    settings = make_settings()
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    api.app.dependency_overrides[api.get_sync_service] = lambda: sync_service
    api.app.dependency_overrides[api.get_extractor] = lambda: extractor
    yield TestClient(api.app), settings
    api.app.dependency_overrides.clear()


def test_health(client):
    test_client, _ = client
    assert test_client.get("/health").json() == {"status": "ok"}


def test_sync_endpoint_creates_tasks(client, fake_jira):
    test_client, _ = client
    response = test_client.post(
        "/tasks",
        json={"meeting_id": "m1", "action_items": [{"summary": "Write the rollback plan"}]},
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "created"
    assert len(fake_jira.issues) == 1


def test_sync_endpoint_validates_input(client):
    test_client, _ = client
    assert test_client.post("/tasks", json={"action_items": []}).status_code == 422
    assert test_client.post("/tasks", json={"action_items": [{"summary": "  "}]}).status_code == 422


def test_api_key_is_enforced_when_configured(client, monkeypatch):
    test_client, _ = client
    secured = make_settings(service_api_key=SecretStr("s3cret"))
    monkeypatch.setattr(api, "get_settings", lambda: secured)
    body = {"action_items": [{"summary": "x"}]}

    assert test_client.post("/tasks", json=body).status_code == 401
    assert test_client.post("/tasks", json=body, headers={"X-API-Key": "nope"}).status_code == 401
    assert test_client.post("/tasks", json=body, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_transcript_endpoint_uses_meeting_date(client, extractor, fake_jira):
    test_client, _ = client
    response = test_client.post(
        "/tasks/from-transcript",
        json={"transcript": "Eve: I'll write the rollback plan.", "meeting_date": "2025-07-02"},
    )
    assert response.status_code == 200
    assert extractor.dates == [date(2025, 7, 2)]
    assert len(fake_jira.issues) == 1


def test_extraction_failure_is_a_502_not_an_empty_result(client, extractor):
    test_client, _ = client

    def boom(transcript, meeting_date):
        raise ExtractionError("Could not extract action items: quota exceeded")

    extractor.extract = boom
    response = test_client.post("/tasks/from-transcript", json={"transcript": "hello"})
    assert response.status_code == 502
    assert "quota exceeded" in response.json()["detail"]


def test_no_action_items(client, extractor):
    test_client, _ = client
    extractor.items = []
    response = test_client.post("/tasks/from-transcript", json={"transcript": "just chatting"})
    assert response.json() == {"message": "No action items found in the transcript.", "results": []}


def test_legacy_plain_text_endpoint_still_works(client, fake_jira):
    test_client, _ = client
    response = test_client.post(
        "/create-jira-tasks",
        content="Eve: I'll write the rollback plan.",
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 200
    assert len(fake_jira.issues) == 1


def test_project_key_must_be_jql_safe():
    with pytest.raises(ValueError):
        make_settings(jira_project_key='POC" OR project = "SECRET')
