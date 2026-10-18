"""GitHub: public repositories - open-source projects, their descriptions, activity and popularity. Part of the
software pack. A project's releases are better followed with the feed adapter (https://github.com/<o>/<r>/releases.atom)."""

from __future__ import annotations

import re
from typing import Any

import kit

NAME = "github"


def search(query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]) -> list[dict[str, Any]]:
    terms = [query]
    if filters.get("language"):
        if not re.fullmatch(r"[A-Za-z0-9+#.\- ]+", filters["language"]):
            raise kit.AdapterError(f"{NAME}: language must be a plain language name like python or c++")
        terms.append(f'language:"{filters["language"]}"')
    if filters.get("minStars"):
        if not filters["minStars"].isdigit():
            raise kit.AdapterError(f"{NAME}: minStars must be a whole number")
        terms.append(f"stars:>={filters['minStars']}")
    if filters.get("created"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", filters["created"]):
            raise kit.AdapterError(f"{NAME}: created must be a date, YYYY-MM-DD")
        terms.append(f"created:>={filters['created']}")
    if since:
        terms.append(f"pushed:>={since}")
    if filters.get("sort") not in (None, "stars", "updated"):
        raise kit.AdapterError(f"{NAME}: sort is stars or updated; leave it out for best match")
    # A token (GITHUB_TOKEN, or the user's gh login lent by the scout for one run) raises the search limit from
    # 10 to 30 requests a minute; it is sent only to api.github.com and never stored.
    headers = {"Authorization": f"Bearer {options['key']}"} if options.get("key") else None
    data = kit.fetch_json("https://api.github.com/search/repositories",
                          {"q": " ".join(terms), "sort": filters.get("sort"), "per_page": min(max(limit, 1), 100)}, options["interval"], headers)

    def convert(repo: dict[str, Any]) -> dict[str, Any]:
        return kit.record(
            NAME, repo["full_name"], repo["html_url"], "documentation", authors=[(repo.get("owner") or {}).get("login", "")],
            date=kit.iso_date(repo.get("pushed_at")), abstract=repo.get("description") or "",
            extra={"stars": repo.get("stargazers_count", 0), "language": repo.get("language"), "topics": repo.get("topics", []),
                   "created": kit.iso_date(repo.get("created_at")),
                   "archived": bool(repo.get("archived")), "license": (repo.get("license") or {}).get("spdx_id"), "dateIs": "last push"},
        )

    return kit.each(data.get("items", []), convert)
