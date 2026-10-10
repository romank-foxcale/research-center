"""Page watch: one web page whose text is fingerprinted, so a refresh notices when it changes - a pricing page,
a policy, a law's consolidated text, a dataset landing page. The query is the page's URL."""

from __future__ import annotations

import re
from typing import Any

import kit

NAME = "page-watch"


def search(query: str, filters: dict[str, str], since: str | None, limit: int, options: dict[str, Any]) -> list[dict[str, Any]]:
    if not query.startswith(("http://", "https://")):
        raise kit.AdapterError(f"{NAME}: the query must be the page's http(s) URL")
    data, kind = kit.fetch(query, interval=options["interval"])
    raw = data.decode("utf-8", errors="replace")
    if kind in ("text/html", "application/xhtml+xml"):
        title = kit.strip_html((re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL) or [None, ""])[1])
        body = kit.strip_html(raw)
    elif kind.startswith("text/") or kind in ("application/json", "application/xml"):
        title, body = "", " ".join(raw.split())
    else:
        raise kit.AdapterError(f"{NAME}: cannot fingerprint content type {kind}")
    return [kit.record(NAME, title or query, query, filters.get("evidenceType", "unknown"), abstract=body[:400],
                       extra={"sha256": kit.sha256(body), "checkedAt": kit.today(), "characters": len(body)})]
