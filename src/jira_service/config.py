from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jira_url: str = Field(description="e.g. https://your-team.atlassian.net")
    jira_email: str
    jira_api_token: SecretStr
    # Validated so it can be placed in JQL safely.
    jira_project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,19}$")
    jira_issue_type: str = "Task"

    google_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"

    # When set, callers must send it in the X-API-Key header (the MCP hub does).
    service_api_key: SecretStr | None = None

    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
