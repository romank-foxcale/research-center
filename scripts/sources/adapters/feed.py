"""Feed: the items of any RSS 2.0, RSS 1.0 (RDF) or Atom feed - a journal, a regulator, a blog, a lab, a newsroom.
The query is the feed's URL."""

from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import Element

import kit

NAME = "feed"


def text(element: Element, *names: str) -> str:
    """The text of the first child whose local tag is one of names."""
    for child in element:
        if kit.local(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return ""


def link(element: Element) -> str:
    for child in element:
        if kit.local(child.tag) != "link":
            continue
        if child.get("href") and child.get("rel", "alternate") == "alternate":
            return child.get("href")
        if (child.text or "").strip():
            return child.text.strip()
    return text(element, "guid", "id")


def authors(element: Element) -> list[str]:
    names = []
    for child in element:
        if kit.local(child.tag) in ("author", "creator"):
            names.append(text(child, "name") or (child.text or "").strip())
    return [name for name in names if name]


def search(
    query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]
) -> list[dict[str, Any]]:
    if not query.startswith(("http://", "https://")):
        raise kit.AdapterError(f"{NAME}: the query must be the feed's http(s) URL")
    data, _ = kit.fetch(query, interval=options["interval"])
    root = kit.xml_root(data)
    items = [element for element in root.iter() if kit.local(element.tag) in ("item", "entry")]
    evidence = filters.get("evidenceType", "unknown")
    results = kit.each(
        items[: max(limit, 1)],
        lambda item: kit.record(
            NAME,
            text(item, "title") or link(item),
            link(item),
            evidence,
            authors=authors(item),
            date=kit.iso_date(text(item, "pubDate", "published", "updated", "date")),
            abstract=kit.strip_html(text(item, "description", "summary", "content", "encoded"))[:2000],
            extra={"feed": query},
        ),
    )
    return kit.after(results, since)
