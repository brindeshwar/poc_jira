import logging
import secrets
from datetime import date
from functools import lru_cache

import uvicorn
from fastapi import Body, Depends, FastAPI, Header, HTTPException, status

from jira_service.config import get_settings
from jira_service.extractor import ActionItemExtractor, ExtractionError, GeminiExtractor
from jira_service.jira_api import JiraAPI
from jira_service.models import SyncRequest, SyncResponse, TranscriptRequest
from jira_service.sync import TaskSyncService

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Jira Task Service",
    description=(
        "Creates or updates Jira tasks from meeting action items. Re-sending the same meeting "
        "is idempotent: each action item maps to one ticket via a stable label."
    ),
    version="0.2.0",
)


@lru_cache
def get_sync_service() -> TaskSyncService:
    settings = get_settings()
    jira = JiraAPI(
        settings.jira_url, settings.jira_email, settings.jira_api_token.get_secret_value()
    )
    return TaskSyncService(jira, settings.jira_project_key, settings.jira_issue_type)


@lru_cache
def get_extractor() -> ActionItemExtractor:
    settings = get_settings()
    if settings.google_api_key is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Transcript extraction needs GOOGLE_API_KEY."
        )
    return GeminiExtractor(
        settings.google_api_key.get_secret_value(),
        settings.gemini_model,
        settings.gemini_thinking_level,
    )


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().service_api_key
    if expected is None:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected.get_secret_value()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tasks", response_model=SyncResponse, dependencies=[Depends(require_api_key)])
def sync_tasks(
    request: SyncRequest, sync: TaskSyncService = Depends(get_sync_service)
) -> SyncResponse:
    """Create or update one Jira task per action item. Used by the MCP meeting hub."""
    return sync.sync(
        request.action_items,
        meeting_id=request.meeting_id,
        meeting_title=request.meeting_title,
        dry_run=request.dry_run,
    )


@app.post(
    "/tasks/from-transcript",
    response_model=SyncResponse,
    dependencies=[Depends(require_api_key)],
)
def sync_from_transcript(
    request: TranscriptRequest,
    sync: TaskSyncService = Depends(get_sync_service),
    extractor: ActionItemExtractor = Depends(get_extractor),
) -> SyncResponse:
    """Extract action items from a raw transcript with Gemini, then sync them to Jira."""
    return _extract_and_sync(
        request.transcript,
        request.meeting_date or date.today(),
        request.meeting_title,
        request.dry_run,
        sync,
        extractor,
    )


@app.post(
    "/create-jira-tasks",
    response_model=SyncResponse,
    dependencies=[Depends(require_api_key)],
    deprecated=True,
)
def legacy_create_jira_tasks(
    transcript: str = Body(..., media_type="text/plain", min_length=1, max_length=200_000),
    sync: TaskSyncService = Depends(get_sync_service),
    extractor: ActionItemExtractor = Depends(get_extractor),
) -> SyncResponse:
    """Original v1 endpoint (plain-text body). Prefer `/tasks/from-transcript`."""
    return _extract_and_sync(transcript, date.today(), None, False, sync, extractor)


def _extract_and_sync(
    transcript: str,
    meeting_date: date,
    meeting_title: str | None,
    dry_run: bool,
    sync: TaskSyncService,
    extractor: ActionItemExtractor,
) -> SyncResponse:
    if not transcript.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Transcript cannot be blank.")
    try:
        items = extractor.extract(transcript, meeting_date)
    except ExtractionError as exc:
        logger.exception("Action item extraction failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not items:
        return SyncResponse(message="No action items found in the transcript.", results=[])
    return sync.sync(items, meeting_title=meeting_title, dry_run=dry_run)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
