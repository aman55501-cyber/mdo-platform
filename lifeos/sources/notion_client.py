"""Minimal Notion REST client for LIFEOS.

The token is read lazily from NOTION_TOKEN so a missing credential degrades the
Notion panels to UNREACHABLE (rule 2) rather than stopping the run or the import.
Nothing here prints the token.

The IDs in the brief are *data-source* IDs. Depending on the workspace's API
version these are queried either at /v1/databases/{id}/query (classic, 2022-06-28)
or /v1/data_sources/{id}/query (2025-09-03). We try classic first and fall back,
recording which worked — so this keeps working whichever the live token uses.

Property extraction is generic: helpers turn a Notion page's property object into
plain Python (title/text/select/status/checkbox/date/url/relation), matching the
real schemas fetched from the workspace.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

_CLASSIC_VERSION = "2022-06-28"
_DATASOURCE_VERSION = "2025-09-03"
_BASE = "https://api.notion.com"


class NotionError(RuntimeError):
    pass


def _token() -> str:
    tok = os.environ.get("NOTION_TOKEN", "").strip()
    if not tok:
        raise NotionError("NOTION_TOKEN not set in .env")
    return tok


def query_data_source(
    data_source_id: str,
    *,
    filter_: Optional[dict] = None,
    sorts: Optional[list[dict]] = None,
    page_size: int = 100,
) -> list[dict]:
    """Return all page objects for a data source, following pagination.

    Tries the classic databases endpoint, then the data_sources endpoint. Any HTTP
    or network failure raises NotionError (caught upstream by guarded())."""
    bearer = _token()
    body: dict[str, Any] = {"page_size": page_size}
    if filter_:
        body["filter"] = filter_
    if sorts:
        body["sorts"] = sorts

    attempts = [
        (f"/v1/databases/{data_source_id}/query", _CLASSIC_VERSION),
        (f"/v1/data_sources/{data_source_id}/query", _DATASOURCE_VERSION),
    ]
    last_error: Exception | None = None
    for path, version in attempts:
        try:
            return _query_paginated(path, version, bearer, body)
        except httpx.HTTPStatusError as exc:
            # 404 (wrong endpoint for this API version) -> try the next style.
            if exc.response.status_code in (400, 404):
                last_error = exc
                continue
            raise NotionError(f"{exc.response.status_code} {path}") from exc
    raise NotionError(f"query failed for {data_source_id}: {last_error}")


def create_page(data_source_id: str, properties: dict) -> dict:
    """Create a page (row) in a data source. Used for the Inbox capture writes —
    the only writes LIFEOS makes, and only ones the user initiated (rule 4). Tries
    the classic parent shape then the data_source shape."""
    bearer = _token()
    attempts = [
        ({"database_id": data_source_id}, _CLASSIC_VERSION),
        ({"type": "data_source_id", "data_source_id": data_source_id}, _DATASOURCE_VERSION),
    ]
    last_error: Exception | None = None
    for parent, version in attempts:
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Notion-Version": version,
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(base_url=_BASE, timeout=30) as client:
                resp = client.post(
                    "/v1/pages", headers=headers,
                    json={"parent": parent, "properties": properties},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                last_error = exc
                continue
            raise NotionError(f"{exc.response.status_code} create_page") from exc
    raise NotionError(f"create_page failed for {data_source_id}: {last_error}")


# property builders for writes
def title_prop(text_value: str) -> dict:
    return {"title": [{"text": {"content": text_value}}]}


def text_prop(text_value: str) -> dict:
    return {"rich_text": [{"text": {"content": text_value}}]}


def select_prop(name: str) -> dict:
    return {"select": {"name": name}}


def _headers(bearer: str, version: str = _CLASSIC_VERSION) -> dict:
    return {"Authorization": f"Bearer {bearer}", "Notion-Version": version,
            "Content-Type": "application/json"}


def list_children(block_id: str) -> list[dict]:
    bearer = _token()
    out: list[dict] = []
    cursor = None
    with httpx.Client(base_url=_BASE, timeout=30) as client:
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            resp = client.get(f"/v1/blocks/{block_id}/children", headers=_headers(bearer), params=params)
            resp.raise_for_status()
            data = resp.json()
            out.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
    return out


def append_children(block_id: str, children: list[dict]) -> dict:
    bearer = _token()
    with httpx.Client(base_url=_BASE, timeout=30) as client:
        resp = client.patch(f"/v1/blocks/{block_id}/children", headers=_headers(bearer),
                            json={"children": children})
        resp.raise_for_status()
        return resp.json()


def delete_block(block_id: str) -> None:
    bearer = _token()
    with httpx.Client(base_url=_BASE, timeout=30) as client:
        resp = client.delete(f"/v1/blocks/{block_id}", headers=_headers(bearer))
        resp.raise_for_status()


def paragraph_block(text_value: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text_value[:1900]}}]}}


def heading_block(text_value: str) -> dict:
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": text_value[:1900]}}]}}


def _query_paginated(path: str, version: str, bearer: str, body: dict) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Notion-Version": version,
        "Content-Type": "application/json",
    }
    results: list[dict] = []
    cursor: Optional[str] = None
    with httpx.Client(base_url=_BASE, timeout=30) as client:
        while True:
            payload = dict(body)
            if cursor:
                payload["start_cursor"] = cursor
            resp = client.post(path, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
    return results


# ── property extractors ───────────────────────────────────────────────────────
def _props(page: dict) -> dict:
    return page.get("properties", {})


def title(page: dict, name: str) -> str:
    arr = _props(page).get(name, {}).get("title", []) or []
    return "".join(p.get("plain_text", "") for p in arr).strip()


def text(page: dict, name: str) -> str:
    arr = _props(page).get(name, {}).get("rich_text", []) or []
    return "".join(p.get("plain_text", "") for p in arr).strip()


def select(page: dict, name: str) -> str:
    val = _props(page).get(name, {}).get("select")
    return (val or {}).get("name", "") if val else ""


def status(page: dict, name: str) -> str:
    val = _props(page).get(name, {}).get("status")
    return (val or {}).get("name", "") if val else ""


def checkbox(page: dict, name: str) -> bool:
    return bool(_props(page).get(name, {}).get("checkbox", False))


def date_start(page: dict, name: str) -> str:
    val = _props(page).get(name, {}).get("date")
    return (val or {}).get("start", "") if val else ""


def url(page: dict, name: str) -> str:
    return _props(page).get(name, {}).get("url", "") or ""


def relation_ids(page: dict, name: str) -> list[str]:
    arr = _props(page).get(name, {}).get("relation", []) or []
    return [r.get("id", "") for r in arr if r.get("id")]


def page_created_time(page: dict) -> str:
    return page.get("created_time", "")
