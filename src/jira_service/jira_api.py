"""Thin client for the Jira Cloud REST API v3."""

from typing import Any

import httpx


class JiraAPIError(RuntimeError):
    pass


class JiraAPI:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=f"{self.base_url}/rest/api/3",
            auth=(email, api_token),
            headers={"Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def search(self, jql: str, fields: list[str], max_results: int = 1) -> list[dict[str, Any]]:
        data = self._request(
            "POST", "/search/jql", json={"jql": jql, "fields": fields, "maxResults": max_results}
        )
        return data.get("issues", [])

    def create_issue(self, fields: dict[str, Any]) -> str:
        return self._request("POST", "/issue", json={"fields": fields})["key"]

    def update_issue(self, key: str, fields: dict[str, Any]) -> None:
        self._request("PUT", f"/issue/{key}", json={"fields": fields})

    def find_users(self, query: str) -> list[dict[str, Any]]:
        users = self._request("GET", "/user/search", params={"query": query, "maxResults": 5})
        return [u for u in users if u.get("active", True) and u.get("accountType") == "atlassian"]

    def browse_url(self, key: str) -> str:
        return f"{self.base_url}/browse/{key}"

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise JiraAPIError(f"Could not reach Jira: {exc}") from exc
        if response.is_error:
            raise JiraAPIError(f"Jira returned {response.status_code}: {_error_text(response)}")
        return response.json() if response.content else None


def _error_text(response: httpx.Response) -> str:
    """Jira puts messages in errorMessages (list) and errors (field -> message)."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    if not isinstance(body, dict):
        return response.text[:300]
    parts = list(body.get("errorMessages", []))
    parts += [f"{field}: {msg}" for field, msg in body.get("errors", {}).items()]
    if body.get("errorMessage"):  # gateway-level errors, e.g. a deactivated site
        parts.append(body["errorMessage"])
    return "; ".join(parts) or response.text[:300]


def to_adf(text: str) -> dict[str, Any]:
    """Jira v3 needs descriptions in Atlassian Document Format: one paragraph per blank-line-separated block."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs
        ],
    }
