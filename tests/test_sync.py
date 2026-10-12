from jira_service.models import ActionItem
from jira_service.sync import SOURCE_LABEL, task_label

ROLLBACK = ActionItem(summary="Write the rollback plan", assignee="Eve", due_date="2025-07-08")


def test_creates_task_with_labels_assignee_and_due_date(sync_service, fake_jira):
    response = sync_service.sync([ROLLBACK], meeting_id="m1", meeting_title="Eng sync")

    [result] = response.results
    assert result.status == "created"
    assert result.jira_url == "https://example.atlassian.net/browse/POC-1"
    issue = fake_jira.issues["POC-1"]
    assert issue["labels"] == [SOURCE_LABEL, task_label(ROLLBACK.summary, "m1")]
    assert issue["assignee"] == {"accountId": "acc-eve"}
    assert issue["duedate"] == "2025-07-08"
    assert "Eng sync" in issue["description"]["content"][-1]["content"][0]["text"]
    assert response.message == "1 created."


def test_resending_same_meeting_updates_instead_of_duplicating(sync_service, fake_jira):
    sync_service.sync([ROLLBACK], meeting_id="m1")
    second = sync_service.sync([ROLLBACK], meeting_id="m1")

    assert second.results[0].status == "updated"
    assert second.results[0].jira_key == "POC-1"
    assert len(fake_jira.issues) == 1


def test_same_summary_in_another_meeting_is_a_new_task(sync_service, fake_jira):
    sync_service.sync([ROLLBACK], meeting_id="m1")
    other = sync_service.sync([ROLLBACK], meeting_id="m2")
    assert other.results[0].status == "created"
    assert len(fake_jira.issues) == 2


def test_update_never_clears_fields_the_meeting_did_not_mention(sync_service, fake_jira):
    sync_service.sync([ROLLBACK], meeting_id="m1")
    sync_service.sync([ActionItem(summary="Write the rollback plan")], meeting_id="m1")

    issue = fake_jira.issues["POC-1"]
    assert issue["assignee"] == {"accountId": "acc-eve"}
    assert issue["duedate"] == "2025-07-08"


def test_label_ignores_case_and_whitespace():
    assert task_label("Write  the Rollback plan ", "m1") == task_label(
        "write the rollback plan", "m1"
    )


def test_ambiguous_or_unknown_assignee_is_left_unassigned_with_warning(sync_service, fake_jira):
    response = sync_service.sync(
        [
            ActionItem(summary="Budget proposal", assignee="Bob"),
            ActionItem(summary="Shortlist influencers", assignee="Charlie"),
        ],
        meeting_id="m1",
    )
    bob, charlie = response.results
    assert "several Jira users" in bob.warnings[0]
    assert "No Jira user" in charlie.warnings[0]
    assert "assignee" not in fake_jira.issues["POC-1"]


def test_app_accounts_are_never_assigned(sync_service, fake_jira):
    sync_service.sync([ActionItem(summary="Task", assignee="Eve")], meeting_id="m1")
    assert fake_jira.issues["POC-1"]["assignee"] == {"accountId": "acc-eve"}


def test_dry_run_reports_without_writing(sync_service, fake_jira):
    sync_service.sync([ROLLBACK], meeting_id="m1")
    response = sync_service.sync(
        [ROLLBACK, ActionItem(summary="New thing")], meeting_id="m1", dry_run=True
    )
    assert [r.status for r in response.results] == ["would_update", "would_create"]
    assert fake_jira.writes == [("create", "POC-1")]
    assert response.message == "Dry run: 1 would create, 1 would update."


def test_jira_errors_fail_only_that_item(sync_service, fake_jira):
    fake_jira.fail_create = True
    response = sync_service.sync([ROLLBACK], meeting_id="m1")
    [result] = response.results
    assert result.status == "failed"
    assert "duedate: Invalid date" in result.message
    assert response.message == "1 failed."


def test_gateway_error_message_is_readable(fake_jira, sync_service):
    import httpx

    from jira_service.jira_api import JiraAPI, JiraAPIError

    api = JiraAPI(
        "https://gone.atlassian.net",
        "e",
        "t",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(404, json={"errorMessage": "Site temporarily unavailable"})
        ),
    )
    try:
        api.search("project = X", ["summary"])
    except JiraAPIError as exc:
        assert str(exc) == "Jira returned 404: Site temporarily unavailable"
    else:
        raise AssertionError("expected JiraAPIError")
