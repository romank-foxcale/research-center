"""Crossref: DOI metadata from publishers of every field, including retraction and correction notices."""

from __future__ import annotations

from typing import Any

import kit

API = "https://api.crossref.org/works"
NAME = "crossref"
WITHDRAWN = ("retraction", "removal", "withdrawal")


def evidence_type(item: dict[str, Any]) -> str:
    kind = item.get("type") or ""
    if kind == "posted-content":
        return "preprint" if item.get("subtype") == "preprint" else "commentary"
    return {
        "journal-article": "peer-reviewed",
        "proceedings-article": "peer-reviewed",
        "book": "book",
        "book-chapter": "book",
        "monograph": "book",
        "edited-book": "book",
        "reference-book": "reference",
        "report": "report",
        "report-component": "report",
        "dataset": "dataset",
        "standard": "standard",
        "dissertation": "thesis",
    }.get(kind, "unknown")


def to_record(item: dict[str, Any]) -> dict[str, Any]:
    dated = next(
        (
            item[field]
            for field in ("published", "issued", "posted", "created")
            if (item.get(field) or {}).get("date-parts")
        ),
        {},
    )
    updates = [{"type": update.get("type"), "doi": update.get("DOI")} for update in item.get("updated-by") or []]
    return kit.record(
        NAME,
        (item.get("title") or [""])[0],
        ((item.get("resource") or {}).get("primary") or {}).get("URL") or item.get("URL", ""),
        evidence_type(item),
        doi=item.get("DOI"),
        authors=[
            " ".join(part for part in (author.get("given"), author.get("family")) if part) or author.get("name", "")
            for author in item.get("author") or []
        ],
        date=kit.iso_date((dated.get("date-parts") or [[]])[0]),
        abstract=kit.strip_html(item.get("abstract", "")),
        extra={
            "publisher": item.get("publisher"),
            "venue": (item.get("container-title") or [None])[0],
            "citedByCount": item.get("is-referenced-by-count", 0),
            "updatedBy": updates,
            "retracted": any(update["type"] in WITHDRAWN for update in updates),
        },
    )


def retracted(dois: list[str], options: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The DOIs among dois that a retraction, removal or withdrawal notice updates, with those notices.
    Asked 50 at a time; Crossref carries the Retraction Watch data in each work's updated-by."""
    found: dict[str, list[dict[str, Any]]] = {}
    unique = sorted({doi for doi in (kit.bare_doi(value) for value in dois) if doi})
    for start in range(0, len(unique), 50):
        chunk = unique[start : start + 50]
        data = kit.fetch_json(
            API,
            {
                "filter": ",".join(f"doi:{doi}" for doi in chunk),
                "rows": len(chunk),
                "mailto": options.get("contactEmail"),
            },
            options["interval"],
        )
        for item in (data.get("message") or {}).get("items", []):
            notices = [
                {"type": update.get("type"), "doi": update.get("DOI")}
                for update in item.get("updated-by") or []
                if update.get("type") in WITHDRAWN
            ]
            if notices and kit.bare_doi(item.get("DOI")):
                found[kit.bare_doi(item["DOI"])] = notices
    return found


def search(
    query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]
) -> list[dict[str, Any]]:
    clauses = []
    if since:
        clauses.append(f"from-pub-date:{since}")
    if filters.get("type"):
        clauses.append(f"type:{filters['type']}")
    data = kit.fetch_json(
        API,
        {
            "query": query,
            "rows": min(max(limit, 1), 100),
            "filter": ",".join(clauses),
            "mailto": options.get("contactEmail"),
        },
        options["interval"],
    )
    return kit.each((data.get("message") or {}).get("items", []), to_record)
