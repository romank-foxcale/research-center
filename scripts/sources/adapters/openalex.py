"""OpenAlex: scholarly works of every field (CC0 metadata), with references and citations for snowballing."""

from __future__ import annotations

from typing import Any

import kit

API = "https://api.openalex.org/works"
NAME = "openalex"


def evidence_type(work: dict[str, Any]) -> str:
    kind = work.get("type") or ""
    source = ((work.get("primary_location") or {}).get("source") or {}).get("type") or ""
    if kind == "article":
        return (
            "peer-reviewed"
            if source in ("journal", "conference")
            else "preprint"
            if source == "repository"
            else "unknown"
        )
    return {
        "review": "review",
        "preprint": "preprint",
        "book": "book",
        "book-chapter": "book",
        "monograph": "book",
        "dataset": "dataset",
        "report": "report",
        "standard": "standard",
        "dissertation": "thesis",
        "letter": "commentary",
        "editorial": "commentary",
    }.get(kind, "unknown")


def abstract(index: dict[str, list[int]] | None) -> str:
    """OpenAlex ships abstracts as an inverted index {word: [positions]}; put the words back in order."""
    if not index:
        return ""
    positions = {position: word for word, places in index.items() for position in places}
    return " ".join(positions[position] for position in sorted(positions))


def to_record(work: dict[str, Any]) -> dict[str, Any]:
    location = work.get("primary_location") or {}
    url = work.get("doi") or location.get("landing_page_url") or work["id"]
    return kit.record(
        NAME,
        work.get("display_name") or work.get("title") or "",
        url,
        evidence_type(work),
        doi=work.get("doi"),
        authors=[(item.get("author") or {}).get("display_name", "") for item in work.get("authorships") or []],
        date=kit.iso_date(work.get("publication_date") or work.get("publication_year")),
        abstract=abstract(work.get("abstract_inverted_index")),
        extra={
            "openalexId": work["id"].rsplit("/", 1)[-1],
            "venue": (location.get("source") or {}).get("display_name"),
            "citedByCount": work.get("cited_by_count", 0),
            "retracted": bool(work.get("is_retracted")),
            "openAccessUrl": (work.get("open_access") or {}).get("oa_url"),
            "language": work.get("language"),
        },
    )


def params(options: dict[str, Any], limit: int, **extra: Any) -> dict[str, Any]:
    return {"per-page": min(max(limit, 1), 50), "mailto": options.get("contactEmail"), **extra}


def search(
    query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]
) -> list[dict[str, Any]]:
    clauses = []
    if since:
        clauses.append(f"from_publication_date:{since}")
    if filters.get("type"):
        clauses.append(f"type:{filters['type']}")
    if filters.get("language"):
        clauses.append(f"language:{filters['language']}")
    if filters.get("oa") == "true":
        clauses.append("is_oa:true")
    data = kit.fetch_json(API, params(options, limit, search=query, filter=",".join(clauses)), options["interval"])
    return kit.each(data.get("results", []), to_record)


def related(item: dict[str, Any], direction: str, limit: int, options: dict[str, Any]) -> list[dict[str, Any]]:
    """backward: the works it cites; forward: the works citing it, most cited first."""
    work_id = item.get("extra", {}).get("openalexId")
    if not work_id and item.get("doi"):
        # A record another adapter found: resolve its DOI to the OpenAlex work first.
        work_id = kit.fetch_json(
            f"{API}/doi:{item['doi']}", {"select": "id", "mailto": options.get("contactEmail")}, options["interval"]
        )["id"].rsplit("/", 1)[-1]
    if not work_id:
        raise kit.AdapterError(f"{NAME}: record {item.get('title', '')[:60]!r} has neither an openalexId nor a DOI")
    if direction == "forward":
        data = kit.fetch_json(
            API, params(options, limit, filter=f"cites:{work_id}", sort="cited_by_count:desc"), options["interval"]
        )
        return kit.each(data.get("results", []), to_record)
    work = kit.fetch_json(
        f"{API}/{work_id}", {"select": "referenced_works", "mailto": options.get("contactEmail")}, options["interval"]
    )
    references = [reference.rsplit("/", 1)[-1] for reference in work.get("referenced_works") or []][
        : min(max(limit, 1), 50)
    ]
    if not references:
        return []
    data = kit.fetch_json(API, params(options, limit, filter=f"openalex:{'|'.join(references)}"), options["interval"])
    return kit.each(data.get("results", []), to_record)
