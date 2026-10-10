"""GDELT: worldwide online news in many languages, the last three months, newest first."""

from __future__ import annotations

import datetime
import re
from typing import Any

import kit

NAME = "gdelt"
WINDOW_DAYS = 90


def search(query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]) -> list[dict[str, Any]]:
    terms = [query]
    for key, operator in (("language", "sourcelang"), ("country", "sourcecountry")):
        if filters.get(key):
            if not re.fullmatch(r"[A-Za-z ]+", filters[key]):
                raise kit.AdapterError(f"{NAME}: {key} must be a plain name like german or france")
            terms.append(f"{operator}:{filters[key].replace(' ', '')}")
    oldest = datetime.date.today() - datetime.timedelta(days=WINDOW_DAYS - 1)
    start = max(datetime.date.fromisoformat(since), oldest) if since else None
    data = kit.fetch_json("https://api.gdeltproject.org/api/v2/doc/doc", {
        "query": " ".join(terms), "mode": "artlist", "format": "json", "sort": "datedesc",
        "maxrecords": min(max(limit, 1), 250), "startdatetime": start.strftime("%Y%m%d000000") if start else None,
    }, options["interval"])
    return kit.each(data.get("articles", []), lambda article: kit.record(
        NAME, article.get("title", ""), article.get("url", ""), "journalism", date=kit.iso_date(article.get("seendate")),
        extra={"domain": article.get("domain"), "language": article.get("language"), "country": article.get("sourcecountry")}))
