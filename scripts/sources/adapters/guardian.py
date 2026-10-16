"""The Guardian: news, analysis and features from one newsroom since 1999 (Open Platform API). Part of the news
pack. Needs a free developer key in GUARDIAN_API_KEY; it reaches search() as options["key"] and is never stored."""

from __future__ import annotations

from typing import Any

import kit

NAME = "guardian"
API = "https://content.guardianapis.com/search"
# Sections whose pieces are opinion rather than reporting.
OPINION = {"commentisfree", "opinion"}


def to_record(item: dict[str, Any]) -> dict[str, Any]:
    fields = item.get("fields") or {}
    opinion = item.get("sectionId") in OPINION
    return kit.record(
        NAME, item["webTitle"], item["webUrl"], "commentary" if opinion else "journalism",
        authors=[fields["byline"]] if fields.get("byline") else [], date=kit.iso_date(item.get("webPublicationDate")),
        abstract=kit.strip_html(fields.get("trailText", "")),
        extra={"section": item.get("sectionName"), "type": item.get("type"), "id": item.get("id")},
    )


def search(query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]) -> list[dict[str, Any]]:
    if filters.get("section") and not filters["section"].replace("-", "").isalnum():
        raise kit.AdapterError(f"{NAME}: section is a Guardian section id like business or world")
    data = kit.fetch_json(API, {
        "q": query, "api-key": options.get("key"), "page-size": min(max(limit, 1), 50), "order-by": "relevance",
        "from-date": since, "section": filters.get("section"), "show-fields": "trailText,byline",
    }, options["interval"])
    response = data.get("response") or {}
    if response.get("status") not in (None, "ok"):
        raise kit.AdapterError(f"{NAME}: {response.get('message', 'the API refused the request')}")
    return kit.each(response.get("results", []), to_record)
