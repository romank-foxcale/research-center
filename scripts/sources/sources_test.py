#!/usr/bin/env python3
"""Test the source adapters offline against recorded-shape fixtures: every adapter maps its API's answer to the
record shape, malformed results are skipped, filters and since reach the API, records merge on DOI or canonical
URL, failures are logged and raised, untrusted XML is refused, and no request goes out with data the user did
not set. No test touches the network."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FIXTURES = HERE / "fixtures"
sys.path[:0] = [str(HERE), str(HERE / "adapters")]
import kit  # noqa: E402
import sources  # noqa: E402

REQUESTS: list[str] = []
# Where adapter searches run: a template-like folder holding only the default adapters, set in main(), so the test
# gives the same result in the template and inside any instance (whatever it enabled or configured).
ROOT = REPO
ROUTES = [  # (part of the URL, fixture, content type); the first match wins
    ("https://api.openalex.org/works/W100", "openalex-work.json", "application/json"),
    ("https://api.openalex.org/works/doi:", "openalex-doi.json", "application/json"),
    ("filter=openalex", "openalex-list.json", "application/json"),
    ("filter=cites", "openalex-citers.json", "application/json"),
    ("https://api.openalex.org/works", "openalex-search.json", "application/json"),
    ("https://api.crossref.org/works?filter=doi", "crossref-dois.json", "application/json"),
    ("https://api.crossref.org/works", "crossref.json", "application/json"),
    ("https://en.wikipedia.org/w/api.php", "wikipedia.json", "application/json"),
    ("https://openlibrary.org/search.json", "openlibrary.json", "application/json"),
    ("https://api.gdeltproject.org/api/v2/doc/doc?query=short", "gdelt-error.txt", "text/plain"),
    ("https://api.gdeltproject.org/api/v2/doc/doc", "gdelt.json", "application/json"),
    ("https://agency.example.org/feed", "rss.xml", "application/rss+xml"),
    ("https://lab.example.org/atom", "atom.xml", "application/atom+xml"),
    ("https://journal.example.org/rdf", "rdf.xml", "application/rdf+xml"),
    ("https://bomb.example.org/feed", "bomb.xml", "application/rss+xml"),
    ("https://gov.example.org/hours", "page.html", "text/html"),
]
PAGES: dict[str, str] = {}  # overrides for page-watch change detection


def transport(url: str) -> tuple[bytes, str]:
    REQUESTS.append(url)
    if url in PAGES:
        return PAGES[url].encode(), "text/html"
    for part, fixture, kind in ROUTES:
        if part in url:
            return (FIXTURES / fixture).read_bytes(), kind
    raise kit.AdapterError(f"no fixture for {url}")


def last_query() -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(REQUESTS[-1]).query))


def raises(error: type[BaseException], function, *args, **kwargs) -> str:
    try:
        function(*args, **kwargs)
    except error as caught:
        return str(caught)
    raise AssertionError(f"{function.__name__} did not raise {error.__name__}")


def test_keys_and_dates() -> None:
    assert kit.canonical_url("HTTP://WWW.Example.org/Path/?b=2&utm_source=x#top") == "https://example.org/Path?b=2"
    assert kit.canonical_url("https://news.example.org/item?id=1") != kit.canonical_url("https://news.example.org/item?id=2")
    assert kit.bare_doi("https://doi.org/10.5555/AbC") == "10.5555/abc" and kit.bare_doi("not a doi") is None
    assert kit.record_key("10.5555/abc", "https://x.org") == "doi:10.5555/abc"
    assert kit.record_key(None, "https://www.x.org/a/") == "url:https://x.org/a"
    for value, expected in [("2025-06-09", "2025-06-09"), ("2026-09-08T00:19:06Z", "2026-09-08"), ("20261002T043000Z", "2026-10-02"),
                            ("Fri, 02 Oct 2026 09:00:00 GMT", "2026-10-02"), ([2025, 12], "2025-12"), (1972, "1972"), ("", ""), ("soon", "")]:
        assert kit.iso_date(value) == expected, (value, kit.iso_date(value))
    assert kit.strip_html("<p>a &amp; <script>x()</script><b>b</b></p>") == "a & b"
    raises(kit.AdapterError, kit.record, "x", "", "https://x.org", "book")
    raises(kit.AdapterError, kit.record, "x", "t", "ftp://x.org", "book")
    raises(kit.AdapterError, kit.record, "x", "t", "https://x.org", "rumour")


def test_scholarly(log: Path) -> None:
    found = sources.search(ROOT, "openalex", "four-day week", {"type": "article"}, "2024-01-01", 50, log)
    assert [item["title"] for item in found] == ["Productivity under a four-day week", "Working paper on compressed weeks"], "untitled skipped"
    first, second = found
    assert first["key"] == "doi:10.5555/wt.2025.1" and first["evidenceType"] == "peer-reviewed" and first["authors"] == ["Ada Example", "Ben Sample"]
    assert first["abstract"] == "Output per hour rose by 7 percent." and first["extra"]["openalexId"] == "W100"
    assert second["evidenceType"] == "preprint" and second["extra"]["retracted"] and second["date"] == "2024"
    query = last_query()
    assert query["filter"] == "from_publication_date:2024-01-01,type:article" and query["search"] == "four-day week"
    assert "mailto" not in query, "no contact email is sent unless the user set one"

    backward = sources.related(ROOT, "openalex", first, "backward", 50, log)
    assert [item["title"] for item in backward] == ["A meta-analysis of compressed schedules"] and backward[0]["evidenceType"] == "review"
    assert last_query()["filter"] == "openalex:W200|W400"
    forward = sources.related(ROOT, "openalex", first, "forward", 50, log)
    assert last_query()["filter"] == "cites:W100" and last_query()["sort"] == "cited_by_count:desc"
    assert [item["extra"]["openalexId"] for item in forward] == ["W500", "W600", "W400"]
    resolved = sources.related(ROOT, "openalex", {"key": "doi:10.5555/wt.2025.1", "title": "found by crossref", "doi": "10.5555/wt.2025.1",
                                                  "extra": {}}, "forward", 50)
    assert any("works/doi:10.5555/wt.2025.1" in url for url in REQUESTS[-2:]) and len(resolved) == 3, "a DOI-only record resolves first"
    raises(kit.AdapterError, sources.related, ROOT, "openalex", {"key": "url:x", "title": "no ids", "extra": {}}, "forward")

    notices = sources.retractions(ROOT, ["https://doi.org/10.5555/Retracted.Trial", "10.5555/new.trial", "not a doi"], log)
    assert notices == {"10.5555/retracted.trial": [{"type": "retraction", "doi": "10.5555/retracted.trial.notice"}]}, \
        "only retraction-type updates count; a correction does not"
    assert last_query()["filter"] == "doi:10.5555/new.trial,doi:10.5555/retracted.trial"
    assert sources.retractions(ROOT, []) == {}
    raises(ValueError, sources.related, ROOT, "crossref", first, "forward")
    raises(ValueError, sources.related, ROOT, "openalex", first, "sideways")

    crossref = sources.search(ROOT, "crossref", "four-day week", {}, "2025-01-01", 50, log)
    assert len(crossref) == 2, "untitled skipped"
    article, comment = crossref
    assert article["abstract"] == "Output per hour rose ." and article["extra"]["venue"] == "Journal of Working Time"
    assert comment["evidenceType"] == "commentary" and comment["extra"]["retracted"] and comment["date"] == "2025-12"
    assert comment["authors"] == ["Editorial Team"] and comment["url"] == "https://news.example.org/four-day-teachers"
    assert last_query()["filter"] == "from-pub-date:2025-01-01"

    merged = sources.merge(found + crossref)
    assert len(merged) == 3 and merged[0]["foundBy"] == ["openalex", "crossref"], "the same DOI merges across adapters"
    flagged = sources.merge([found[0], {**crossref[0], "extra": {**crossref[0]["extra"], "retracted": True}}])
    assert flagged[0]["extra"]["retracted"] and not found[0]["extra"]["retracted"], "a retraction flag survives the merge, inputs untouched"


def test_reference_books_news(log: Path) -> None:
    page = sources.search(ROOT, "wikipedia", "four-day week", {}, None, 5, log)[0]
    assert page["url"] == "https://en.wikipedia.org/wiki/Four-day_workweek" and page["abstract"] == "over four days & not five"
    assert page["evidenceType"] == "reference"
    raises(kit.AdapterError, sources.search, ROOT, "wikipedia", "x", {"lang": "en.evil.org/"}, None, 5)

    books = sources.search(ROOT, "openlibrary", "four-day week", {}, "2000-01-01", 5, log)
    assert [book["title"] for book in books] == ["Case for a four day week"], "since keeps 2020, drops 1972 and the keyless doc"

    news = sources.search(ROOT, "gdelt", '"four-day week"', {"language": "english"}, "2000-01-01", 5, log)
    assert [item["date"] for item in news] == ["2026-10-02", "2026-10-01"] and news[0]["evidenceType"] == "journalism"
    assert news[0]["key"] == "url:https://news.example.org/a?id=1", "tracking parameters do not split a page"
    query = last_query()
    assert query["query"] == '"four-day week" sourcelang:english'
    assert query["startdatetime"] > "20000101000000", "since older than GDELT's window is clamped to it"
    raises(kit.AdapterError, sources.search, ROOT, "gdelt", "x", {"country": "fr; DROP"}, None, 5)
    message = raises(kit.AdapterError, sources.search, ROOT, "gdelt", "short", {}, None, 5, log)
    assert "too short" in message, message


def test_feeds_and_pages(log: Path) -> None:
    rss = sources.search(ROOT, "feed", "https://agency.example.org/feed", {"evidenceType": "official-statistics"}, None, 10, log)
    assert [item["url"] for item in rss] == ["https://agency.example.org/stats/2026", "https://agency.example.org/stats/2024"]
    assert rss[0]["abstract"] == "Average hours fell ." and rss[0]["authors"] == ["Statistics Office"]
    assert rss[0]["evidenceType"] == "official-statistics" and rss[0]["date"] == "2026-10-02"
    recent = sources.search(ROOT, "feed", "https://agency.example.org/feed", {}, "2026-01-01", 10)
    assert [item["date"] for item in recent] == ["2026-10-02"] and recent[0]["evidenceType"] == "unknown"
    atom = sources.search(ROOT, "feed", "https://lab.example.org/atom", {}, None, 10)
    assert atom[0]["url"] == "https://lab.example.org/pilot" and atom[0]["authors"] == ["Dr. Lab"] and atom[0]["date"] == "2026-09-30"
    rdf = sources.search(ROOT, "feed", "https://journal.example.org/rdf", {}, None, 10)
    assert rdf[0]["title"] == "Article one" and rdf[0]["date"] == "2026-09-15"
    assert "entities" in raises(kit.AdapterError, sources.search, ROOT, "feed", "https://bomb.example.org/feed", {}, None, 10)
    raises(kit.AdapterError, sources.search, ROOT, "feed", "file:///etc/passwd", {}, None, 10)

    url = "https://gov.example.org/hours"
    watched = sources.search(ROOT, "page-watch", url, {"evidenceType": "regulation"}, None, 1, log)[0]
    assert watched["title"] == "Maximum weekly hours – Example Gov" and "tracking" not in watched["abstract"]
    assert "48 hours" in watched["abstract"] and watched["evidenceType"] == "regulation"
    again = sources.search(ROOT, "page-watch", url, {}, None, 1)[0]
    assert again["extra"]["sha256"] == watched["extra"]["sha256"], "the same page keeps its fingerprint"
    PAGES[url] = (FIXTURES / "page.html").read_text(encoding="utf-8").replace("48 hours", "40 hours")
    changed = sources.search(ROOT, "page-watch", url, {}, None, 1)[0]
    assert changed["extra"]["sha256"] != watched["extra"]["sha256"], "a changed page gets a new fingerprint"


def test_contract(log: Path) -> None:
    raises(ValueError, sources.search, ROOT, "openalex", "x", {"bogus": "1"})
    raises(ValueError, sources.search, ROOT, "nope", "x")
    raises(ValueError, sources.search, ROOT, "../runner/rc", "x")
    raises(ValueError, sources.search, ROOT, "openalex", "x", {}, "last week")

    entries = json.loads(log.read_text(encoding="utf-8"))
    assert all(entry["status"] in ("ok", "error") and "at" in entry for entry in entries)
    first = entries[0]
    assert (first["adapter"], first["query"], first["since"], first["count"], first["filters"]) == \
        ("openalex", "four-day week", "2024-01-01", 2, {"type": "article"})
    errors = [entry for entry in entries if entry["status"] == "error"]
    assert errors and errors[-1]["adapter"] == "gdelt" and errors[-1]["count"] == 0 and "too short" in errors[-1]["error"]
    assert any(entry.get("direction") == "backward" for entry in entries), "related lookups are logged too"

    for identifier, spec in sources.descriptors(ROOT).items():
        module = sources.module(spec)
        assert callable(module.search), identifier
        assert hasattr(module, "related") == bool(spec["related"]), f"{identifier}: related flag and module disagree"
        assert hasattr(module, "retracted") == bool(spec.get("retractions")), f"{identifier}: retractions flag and module disagree"

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        # copyfile, not copy2: under Nix the template is read-only and its modes must not carry over.
        shutil.copytree(REPO / "templates" / "adapters", root / "catalog" / "adapters", copy_function=shutil.copyfile)
        settings = json.loads((REPO / "templates" / "research-center.json").read_text(encoding="utf-8"))
        settings["research"]["contactEmail"] = "me@example.org"
        (root / "research-center.json").write_text(json.dumps(settings), encoding="utf-8")
        sources.search(root, "openalex", "x")
        assert last_query()["mailto"] == "me@example.org", "the contact email goes out only once the user set it"
        spec = json.loads((root / "catalog" / "adapters" / "crossref.json").read_text(encoding="utf-8"))
        (root / "catalog" / "adapters" / "crossref.json").write_text(json.dumps({**spec, "needsKeyEnv": "RC_TEST_KEY"}), encoding="utf-8")
        os.environ.pop("RC_TEST_KEY", None)
        assert "RC_TEST_KEY" in raises(kit.AdapterError, sources.search, root, "crossref", "x")

    validator = __import__("importlib.util").util
    spec = validator.spec_from_file_location("validate_rc", REPO / "scripts" / "validate-research-center.py")
    module = validator.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors: list[str] = []
    module.check_adapters(REPO, REPO / "templates" / "adapters", errors)
    assert errors == [], errors
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "adapters").mkdir()
        bad = {**json.loads((REPO / "templates" / "adapters" / "feed.json").read_text(encoding="utf-8")),
               "module": "../../runner/rc", "evidenceTypes": ["rumour"], "watchable": 1, "needsKeyEnv": "sk-live-123"}
        (root / "adapters" / "feed.json").write_text(json.dumps(bad), encoding="utf-8")
        module.check_adapters(root, root / "adapters", errors)
        joined = " ".join(errors)
        assert all(word in joined for word in ("module", "evidenceTypes", "watchable", "needsKeyEnv")), errors


def test_packs_and_own_adapters() -> None:
    """Packs are enabled per instance without touching code; an adapter made with `new` passes its own fixture test;
    every shipped fixture passes."""
    assert sources.run_fixture(REPO, "pubmed") == [] and sources.run_fixture(REPO, "github") == [], "enabled or not"
    previous, kit.TRANSPORT = kit.TRANSPORT, None
    try:
        fixture = json.loads((FIXTURES / "pubmed.fixture.json").read_text(encoding="utf-8"))
        responses = fixture["responses"]
        kit.TRANSPORT = lambda url: next(((json.dumps(item["body"]) if not isinstance(item["body"], str) else item["body"]).encode(),
                                          item.get("contentType", "application/json")) for item in responses if item["match"] in url)
        found = sources.module(sources.packs()["medicine"]["descriptors"]["pubmed"]).search("x", {"type": "Meta-Analysis"}, "2024-01-01", 5,
                                                                                             {"interval": 0})
        assert [item["extra"]["retracted"] for item in found] == [False, True], "a Retracted Publication type flags the record"
        assert found[0]["abstract"] == "Long hours harm health. Wellbeing rose with no loss of output."
        assert found[0]["authors"] == ["Example A"], "collective names are not authors"
    finally:
        kit.TRANSPORT = previous
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        # File by file: under Nix the template is read-only, and copytree would carry that over to the directory.
        (root / "catalog" / "adapters").mkdir(parents=True)
        for path in (REPO / "templates" / "adapters").glob("*.json"):
            shutil.copyfile(path, root / "catalog" / "adapters" / path.name)
        (root / "research-center.json").write_text((REPO / "templates" / "research-center.json").read_text(encoding="utf-8"), encoding="utf-8")
        assert sources.set_pack(root, "medicine", True) == ["pubmed"] and "pubmed" in sources.descriptors(root)
        sources.set_pack(root, "medicine", False)
        assert "pubmed" not in sources.descriptors(root)
        raises(ValueError, sources.set_pack, root, "astrology", True)
        # A folder without research-center.json is the template: packs are enabled only in instances. (Not REPO
        # itself: this test also runs inside instances, where enabling would change the instance.)
        template_like = Path(directory) / "template"
        template_like.mkdir()
        raises(ValueError, sources.set_pack, template_like, "medicine", True)

        written = sources.scaffold(root, "city-council", "regulatory", "regulation")
        assert [path.name for path in written] == ["city-council.json", "city_council.py", "city-council.fixture.json"]
        assert sources.run_fixture(root, "city-council") == [], sources.run_fixture(root, "city-council")
        text = "".join(path.read_text(encoding="utf-8") for path in written)
        assert not any(token in text for token in ("__ID__", "__MODULE__", "__FAMILY__", "__EVIDENCE__")), "every placeholder is filled"
        raises(ValueError, sources.scaffold, root, "openalex", "scholarly", "peer-reviewed")
        raises(ValueError, sources.scaffold, root, "Bad Name", "web", "unknown")
        validator = __import__("importlib.util").util
        spec = validator.spec_from_file_location("validate_rc", REPO / "scripts" / "validate-research-center.py")
        checker = validator.module_from_spec(spec)
        spec.loader.exec_module(checker)
        errors: list[str] = []
        checker.check_adapters(root, root / "catalog" / "adapters", errors)
        assert errors == [], errors
        broken = root / "catalog" / "adapters" / "code" / "city-council.fixture.json"
        broken.write_text(broken.read_text(encoding="utf-8").replace('"count": 1', '"count": 3'), encoding="utf-8")
        assert "expected 3 records, got 1" in " ".join(sources.run_fixture(root, "city-council"))


def test_rate_limit() -> None:
    slept: list[float] = []
    clock, sleep = kit.time.monotonic, kit.time.sleep
    kit.time.monotonic, kit.time.sleep = (lambda: 1000.0), slept.append
    try:
        kit._wait_turn("api.example.org", 5.0)
        kit._wait_turn("api.example.org", 5.0)
        kit._wait_turn("other.example.org", 5.0)
    finally:
        kit.time.monotonic, kit.time.sleep = clock, sleep
    assert slept == [5.0], f"the second request to a host waits its turn; other hosts do not: {slept}"


def main() -> int:
    global ROOT
    kit.TRANSPORT = transport
    isolated = tempfile.TemporaryDirectory()
    ROOT = Path(isolated.name)
    (ROOT / "templates" / "adapters").mkdir(parents=True)
    for path in (REPO / "templates" / "adapters").glob("*.json"):
        shutil.copyfile(path, ROOT / "templates" / "adapters" / path.name)
    test_keys_and_dates()
    test_rate_limit()
    test_packs_and_own_adapters()
    kit.TRANSPORT = transport
    with tempfile.TemporaryDirectory() as directory:
        log = Path(directory) / "searches.json"
        test_scholarly(log)
        test_reference_books_news(log)
        test_feeds_and_pages(log)
        test_contract(log)
    print("sources test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
