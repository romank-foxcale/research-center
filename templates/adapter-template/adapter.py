"""__ID__: an adapter made with ./rc sources new. Point API at the site's search endpoint, map its answer in
to_record, describe it in catalog/adapters/__ID__.json, and keep catalog/adapters/code/__ID__.fixture.json a real
sample of its answer so ./rc sources test __ID__ keeps passing. Read docs/decisions/0007-source-adapters.md.

No credentials in this file: an API key comes from the environment variable the descriptor names in needsKeyEnv,
and reaches search() as options["key"]."""

from __future__ import annotations

from typing import Any

import kit

NAME = "__ID__"
API = "https://api.example.org/search"


def to_record(item: dict[str, Any]) -> dict[str, Any]:
    """One result of the API as a record; kit.each skips results this cannot convert."""
    return kit.record(NAME, item["title"], item["url"], "__EVIDENCE__", doi=item.get("doi"), authors=item.get("authors", []),
                      date=kit.iso_date(item.get("date")), abstract=item.get("summary", ""))


def search(query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]) -> list[dict[str, Any]]:
    data = kit.fetch_json(API, {"q": query, "limit": limit, "from": since}, options["interval"])
    return kit.after(kit.each(data.get("results", []), to_record), since)
