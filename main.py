"""Kept so `uvicorn main:app` keeps working. Prefer `uv run jira-task-service`."""

from jira_service.api import app, main

__all__ = ["app"]

if __name__ == "__main__":
    main()
