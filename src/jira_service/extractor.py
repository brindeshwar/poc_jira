from datetime import date, timedelta
from typing import Protocol

from google import genai
from google.genai import types

from jira_service.models import ActionItem, ExtractedActionItems


class ExtractionError(RuntimeError):
    pass


class ActionItemExtractor(Protocol):
    def extract(self, transcript: str, meeting_date: date) -> list[ActionItem]: ...


PROMPT = """You extract action items from meeting transcripts.

The meeting took place on {meeting_date} ({weekday}). Resolve relative deadlines against that date:
"end of week" / "by Friday" means {friday}; "next week" means the week starting {next_monday}.
Only fill assignee or due_date when the transcript states them; otherwise use null.
An action item is a concrete task someone committed to. Return an empty list if there are none."""


class GeminiExtractor:
    def __init__(self, api_key: str, model: str, thinking_level: str = "low") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._thinking = types.ThinkingConfig(
            thinking_level=types.ThinkingLevel(thinking_level.upper())
        )

    def extract(self, transcript: str, meeting_date: date) -> list[ActionItem]:
        friday = meeting_date + timedelta(days=(4 - meeting_date.weekday()) % 7)
        next_monday = meeting_date + timedelta(days=7 - meeting_date.weekday())
        system = PROMPT.format(
            meeting_date=meeting_date.isoformat(),
            weekday=meeting_date.strftime("%A"),
            friday=friday.isoformat(),
            next_monday=next_monday.isoformat(),
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=f"Transcript:\n{transcript}",
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0,
                    thinking_config=self._thinking,
                    response_mime_type="application/json",
                    response_json_schema=ExtractedActionItems.model_json_schema(),
                ),
            )
            return ExtractedActionItems.model_validate_json(response.text or "").action_items
        except Exception as exc:
            raise ExtractionError(f"Could not extract action items: {exc}") from exc
