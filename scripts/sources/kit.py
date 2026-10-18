"""What every source adapter shares: the record shape, stable record keys, polite HTTP with a test transport,
and small parsers for dates, HTML and XML. Standard library only, so ./rc sources needs no Nix closure.

An adapter is scripts/sources/adapters/<module>.py with
    search(query, filters, since, limit, options) -> list[record]
and optionally
    related(record, direction, limit, options) -> list[record]    (direction: "backward" or "forward")
described by catalog/adapters/<id>.json (docs/decisions/0007-source-adapters.md).
"""

from __future__ import annotations

import datetime
import email.utils
import hashlib
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from typing import Any, Callable

USER_AGENT = "research-center/1 (+https://github.com/romank-foxcale/research-center)"
TIMEOUT = 30
MAX_BYTES = 10 * 1024 * 1024
RETRIES = 2

# What kind of evidence a record is. Domain-agnostic; how much each kind can be trusted is graded later.
EVIDENCE_TYPES = (
    "dataset", "review", "peer-reviewed", "preprint", "thesis", "report", "official-statistics", "regulation",
    "court-ruling", "standard", "company-filing", "documentation", "book", "journalism", "vendor", "commentary",
    "forum", "reference", "unknown",
)
FAMILIES = ("scholarly", "web", "news", "feed", "reference", "books", "code", "data", "legal", "regulatory", "patents")
DIRECTIONS = ("backward", "forward")
TRACKING = re.compile(r"^(utm_[a-z]+|fbclid|gclid|mc_cid|mc_eid|ref_src|igshid)$", re.IGNORECASE)

# Tests replace this with a function(url) -> (bytes, content type) that reads fixtures; None means the network.
TRANSPORT: Callable[[str], tuple[bytes, str]] | None = None


class AdapterError(RuntimeError):
    """A source could not be searched; the message says why and goes into searches.json."""


# Records ----------------------------------------------------------------------------------------------------


def canonical_url(url: str) -> str:
    """One spelling per page: https, lowercase host without www, no fragment, no tracking parameters, no
    trailing slash. The path and the remaining query stay as they are: ?id=1 and ?id=2 are different pages."""
    parts = urllib.parse.urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    query = urllib.parse.urlencode([(key, value) for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                                    if not TRACKING.match(key)])
    path = parts.path.rstrip("/")
    return urllib.parse.urlunsplit(("https", host, path, query, ""))


def bare_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", value.strip(), flags=re.IGNORECASE).lower()
    return doi if doi.startswith("10.") else None


def record_key(doi: str | None, url: str) -> str:
    """The identity records merge on across adapters: the DOI when there is one, else the canonical URL."""
    return f"doi:{doi}" if doi else f"url:{canonical_url(url)}"


def record(adapter: str, title: str, url: str, evidence_type: str, *, doi: str | None = None,
           authors: list[str] | None = None, date: str = "", abstract: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """One search result in the shape every adapter returns."""
    title = " ".join(str(title or "").split())
    if not title:
        raise AdapterError(f"{adapter}: a result has no title")
    if not str(url).startswith(("http://", "https://")):
        raise AdapterError(f"{adapter}: result {title[:60]!r} has no http(s) url")
    if evidence_type not in EVIDENCE_TYPES:
        raise AdapterError(f"{adapter}: unknown evidence type {evidence_type!r}")
    doi = bare_doi(doi)
    return {
        "adapter": adapter, "key": record_key(doi, url), "title": title,
        "authors": [" ".join(name.split()) for name in authors or [] if name and name.strip()],
        "date": date, "url": url, "doi": doi, "evidenceType": evidence_type,
        "abstract": " ".join(abstract.split()), "extra": extra or {},
    }


def each(items: list[Any], convert: Callable[[Any], dict[str, Any]]) -> list[dict[str, Any]]:
    """convert every raw result to a record, skipping the ones that cannot be one (no title, no URL): a single
    malformed entry in an API response never costs the whole search."""
    records = []
    for item in items:
        try:
            records.append(convert(item))
        except (AdapterError, KeyError, TypeError, ValueError, AttributeError):
            continue
    return records


def after(records: list[dict[str, Any]], since: str | None) -> list[dict[str, Any]]:
    """Records dated on or after since (YYYY-MM-DD); undated records are kept, the seen set filters them."""
    if not since:
        return records
    return [item for item in records if not item["date"] or item["date"] >= since[: len(item["date"])]]


# Dates and text ---------------------------------------------------------------------------------------------


def iso_date(value: Any) -> str:
    """YYYY-MM-DD (or YYYY-MM, YYYY) from ISO 8601, RFC 822, Crossref date-parts or a bare year; '' if unknown."""
    if value is None or value == "":
        return ""
    if isinstance(value, (list, tuple)):
        parts = [int(part) for part in value if part is not None][:3]
        return "-".join([f"{parts[0]:04d}", *(f"{part:02d}" for part in parts[1:])]) if parts else ""
    if isinstance(value, int):
        return f"{value:04d}"
    text = str(value).strip()
    match = re.match(r"^(\d{4})(?:-?(\d{2}))?(?:-?(\d{2}))?(?:[T ]|$)", text)
    if match:
        return "-".join(part for part in match.groups() if part)
    try:
        return email.utils.parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return ""


def strip_html(text: str) -> str:
    """Plain text from an HTML or JATS fragment."""
    text = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", text or "", flags=re.IGNORECASE | re.DOTALL)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def xml_root(data: bytes) -> ElementTree.Element:
    """Parse untrusted XML. Entity declarations are refused: they are how XML expands into a memory bomb."""
    if b"<!ENTITY" in data:
        raise AdapterError("the XML declares entities; refused")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise AdapterError(f"not well-formed XML: {error}") from error


def local(tag: str) -> str:
    """An XML tag without its namespace: '{http://www.w3.org/2005/Atom}entry' -> 'entry'."""
    return tag.rsplit("}", 1)[-1]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# HTTP -------------------------------------------------------------------------------------------------------

_last_request: dict[str, float] = {}
_lock = threading.Lock()


def _wait_turn(host: str, interval: float) -> None:
    """At most one request per interval seconds to a host, across threads."""
    with _lock:
        now = time.monotonic()
        start = max(now, _last_request.get(host, 0.0) + interval)
        _last_request[host] = start
    if start > now:
        time.sleep(start - now)


def build_url(url: str, params: dict[str, Any] | None = None) -> str:
    query = {key: value for key, value in (params or {}).items() if value not in (None, "")}
    return f"{url}?{urllib.parse.urlencode(query)}" if query else url


def fetch(url: str, params: dict[str, Any] | None = None, interval: float = 1.0,
          headers: dict[str, str] | None = None) -> tuple[bytes, str]:
    """(body, content type) of a GET, retrying 429 and 5xx; AdapterError when it cannot be had."""
    full = build_url(url, params)
    if TRANSPORT is not None:
        return TRANSPORT(full)
    host = urllib.parse.urlsplit(full).hostname or ""
    for attempt in range(RETRIES + 1):
        _wait_turn(host, interval)
        request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": "*/*", **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise AdapterError(f"{host}: response larger than {MAX_BYTES} bytes")
                return data, response.headers.get_content_type()
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < RETRIES:
                delay = error.headers.get("Retry-After", "")
                # Without Retry-After, back off exponentially but never less than the host's own interval
                # (GDELT allows one request per 5 seconds; a 2-second retry only earns another 429).
                time.sleep(min(int(delay), 30) if delay.isdigit() else max(interval * 2, 2 ** (attempt + 1)))
                continue
            raise AdapterError(f"{host}: HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if attempt < RETRIES:
                time.sleep(2 ** (attempt + 1))
                continue
            raise AdapterError(f"{host}: {getattr(error, 'reason', error)}") from error
    raise AdapterError(f"{host}: no response")


def fetch_json(url: str, params: dict[str, Any] | None = None, interval: float = 1.0,
               headers: dict[str, str] | None = None) -> Any:
    data, _ = fetch(url, params, interval, headers)
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        # Some APIs (GDELT) answer a bad query with a plain-text sentence instead of JSON.
        raise AdapterError(f"not JSON: {data[:200].decode('utf-8', errors='replace').strip()}") from error


def today() -> str:
    return datetime.date.today().isoformat()
