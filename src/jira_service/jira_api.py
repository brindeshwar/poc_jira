"""Thin client for the Jira Cloud REST API v3."""

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRY_STATUSES = {429, 502, 503, 504}
MAX_ATTEMPTS = 3
BULK_LIMIT = 50  # Jira's maximum for POST /issue/bulk


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
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
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

    def bulk_create(self, field_sets: list[dict[str, Any]]) -> list[tuple[str | None, str | None]]:
        """Create up to BULK_LIMIT issues in one call. Returns (key, error) per input, in order.

        Jira reports partial failure in the same response: `issues` holds the created issues in
        input order (minus the failures) and `errors[].failedElementNumber` indexes the failures."""
        if len(field_sets) > BULK_LIMIT:
            raise ValueError(f"bulk_create accepts at most {BULK_LIMIT} issues")
        body = self._request(
            "POST",
            "/issue/bulk",
            json={"issueUpdates": [{"fields": f} for f in field_sets]},
            accept_statuses={400},  # all-failed bulk requests still carry per-element errors
        )
        failures = {
            e["failedElementNumber"]: _element_error(e) for e in (body or {}).get("errors", [])
        }
        created = iter((body or {}).get("issues", []))
        results: list[tuple[str | None, str | None]] = []
        for index in range(len(field_sets)):
            if index in failures:
                results.append((None, failures[index]))
            else:
                issue = next(created, None)
                results.append((issue["key"], None) if issue else (None, "Jira did not create it"))
        return results

    def update_issue(self, key: str, fields: dict[str, Any]) -> None:
        self._request("PUT", f"/issue/{key}", json={"fields": fields})

    def find_users(self, query: str) -> list[dict[str, Any]]:
        users = self._request("GET", "/user/search", params={"query": query, "maxResults": 5})
        return [u for u in users if u.get("active", True) and u.get("accountType") == "atlassian"]

    def browse_url(self, key: str) -> str:
        return f"{self.base_url}/browse/{key}"

    def close(self) -> None:
        self._http.close()

    def _request(
        self, method: str, path: str, *, accept_statuses: set[int] = frozenset(), **kwargs: Any
    ) -> Any:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise JiraAPIError(f"Could not reach Jira: {exc}") from exc
            if response.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                delay = _retry_delay(response, attempt)
                logger.info(
                    "Jira %s on %s %s; retrying in %.1fs", response.status_code, method, path, delay
                )
                self._sleep(delay)
                continue
            if response.is_error and response.status_code not in accept_statuses:
                raise JiraAPIError(f"Jira returned {response.status_code}: {_error_text(response)}")
            return response.json() if response.content else None
        raise AssertionError("unreachable")


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Honour Retry-After (seconds) when Jira sends it; otherwise back off 0.5s, 1s, 2s…"""
    try:
        return min(float(response.headers["Retry-After"]), 30.0)
    except (KeyError, ValueError):
        return 0.5 * 2 ** (attempt - 1)


def _element_error(error: dict[str, Any]) -> str:
    details = error.get("elementErrors", {})
    parts = list(details.get("errorMessages", []))
    parts += [f"{field}: {msg}" for field, msg in details.get("errors", {}).items()]
    return "; ".join(parts) or f"Jira rejected it (status {error.get('status', '?')})"


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
