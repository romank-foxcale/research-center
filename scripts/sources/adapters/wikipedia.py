"""Wikipedia: orientation on any subject and the references its articles cite; never evidence on its own."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

import kit

NAME = "wikipedia"


def search(query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]) -> list[dict[str, Any]]:
    language = filters.get("lang", "en")
    if not re.fullmatch(r"[a-z]{2,3}(-[a-z]+)?", language):
        raise kit.AdapterError(f"{NAME}: lang must be a Wikipedia language code like en or de, not {language!r}")
    data = kit.fetch_json(f"https://{language}.wikipedia.org/w/api.php", {
        "action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": min(max(limit, 1), 50),
        "srprop": "snippet|timestamp",
    }, options["interval"])
    def convert(page: dict[str, Any]) -> dict[str, Any]:
        url = f"https://{language}.wikipedia.org/wiki/{urllib.parse.quote(page['title'].replace(' ', '_'))}"
        return kit.record(NAME, page["title"], url, "reference", abstract=kit.strip_html(page.get("snippet", "")),
                          date=kit.iso_date(page.get("timestamp")), extra={"pageId": page.get("pageid"), "dateIs": "last edit"})

    # The date is the last edit, not a publication, so since does not filter here.
    return kit.each((data.get("query") or {}).get("search", []), convert)
