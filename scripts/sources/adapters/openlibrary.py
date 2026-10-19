"""Open Library: books on any subject, with authors, first publication year and ISBNs."""

from __future__ import annotations

from typing import Any

import kit

NAME = "openlibrary"


def search(
    query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]
) -> list[dict[str, Any]]:
    data = kit.fetch_json(
        "https://openlibrary.org/search.json",
        {
            "q": query,
            "limit": min(max(limit, 1), 100),
            "language": filters.get("language"),
            "fields": "key,title,author_name,first_publish_year,isbn,subject",
        },
        options["interval"],
    )
    results = kit.each(
        data.get("docs", []),
        lambda doc: kit.record(
            NAME,
            doc.get("title", ""),
            f"https://openlibrary.org{doc['key']}",
            "book",
            authors=doc.get("author_name") or [],
            date=kit.iso_date(doc.get("first_publish_year")),
            extra={"isbn": (doc.get("isbn") or [None])[0], "subjects": (doc.get("subject") or [])[:8]},
        ),
    )
    return kit.after(results, since)
