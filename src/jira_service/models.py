from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ActionItem(BaseModel):
    """Shared contract with the MCP meeting hub."""

    summary: str = Field(min_length=1, max_length=255)
    description: str | None = None
    assignee: str | None = Field(None, description="Name or email as said in the meeting.")
    due_date: str | None = Field(None, description="YYYY-MM-DD")

    @field_validator("summary")
    @classmethod
    def _strip_summary(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("summary cannot be blank")
        return value

    @field_validator("due_date")
    @classmethod
    def _iso_date_or_none(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None


class ExtractedActionItems(BaseModel):
    action_items: list[ActionItem]


class SyncRequest(BaseModel):
    action_items: list[ActionItem] = Field(min_length=1, max_length=50)
    meeting_id: str | None = Field(None, max_length=100)
    meeting_title: str | None = Field(None, max_length=200)
    dry_run: bool = False


class TranscriptRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=200_000)
    meeting_title: str | None = Field(None, max_length=200)
    meeting_date: date | None = Field(None, description="Used to resolve 'by Friday' etc.")
    dry_run: bool = False


TaskStatus = Literal["created", "updated", "would_create", "would_update", "failed"]


class TaskResult(BaseModel):
    summary: str
    status: TaskStatus
    jira_key: str | None = None
    jira_url: str | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SyncResponse(BaseModel):
    message: str
    results: list[TaskResult]
