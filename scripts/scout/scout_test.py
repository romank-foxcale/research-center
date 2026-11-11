#!/usr/bin/env python3
"""Test scout discovery: each tag asks GitHub for new and for established active repositories, arXiv for its newest
papers and OpenAlex for recent works; results merge by key across tags; repositories carry the profile's licence
verdict; a failing source is reported and the rest go on; the seen-list makes a find a candidate once; the next run
starts from the last discovery; and an adapter that is not enabled is skipped, not failed."""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path[:0] = [str(HERE), str(SCRIPTS), str(SCRIPTS / "runner"), str(SCRIPTS / "sources")]
import kit  # noqa: E402
import profiles  # noqa: E402
import profiles_test  # noqa: E402  (its instance builder)
import scout  # noqa: E402
import tags  # noqa: E402

CALLS: list[tuple[str, str, dict, str | None]] = []
FAIL = {"openalex"}
PAPERS = iter(range(1, 1000))  # every arXiv answer is a paper never seen before


def repo(name: str, licence: str | None, stars: int) -> dict:
    return kit.record(
        "github",
        name,
        f"https://github.com/{name}",
        "documentation",
        authors=[name.split("/")[0]],
        date="2026-10-10",
        abstract=f"{name} does things",
        extra={
            "stars": stars,
            "language": "Python",
            "topics": [],
            "created": "2026-10-01",
            "archived": False,
            "license": licence,
        },
    )


def fake_search(root, adapter, query, filters, since, limit, log):
    CALLS.append((adapter, query, dict(filters), since))
    if adapter in FAIL:
        raise kit.AdapterError(f"{adapter}: HTTP 429")
    if adapter == "github" and "created" in filters:
        shared = repo("acme/ocr-kit", "MIT", 900)  # found by both tags
        return [shared, repo("acme/gpl-tool", "GPL-3.0", 50)] if "OCR" in query else [shared]
    if adapter == "github":
        return [repo("big/reranker", None, 5000)]
    if adapter == "feed":
        return [
            kit.record(
                "feed",
                f"A paper on {query[-40:]}",
                f"https://arxiv.org/abs/2610.{next(PAPERS):05d}",
                "preprint",
                date="2026-10-12",
            )
        ]
    return []


def quiet(function, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


def test_scout() -> None:
    # Module state outlives a test; a rerun in the same process (mutation testing) starts clean.
    CALLS.clear()
    with tempfile.TemporaryDirectory() as directory:
        root = profiles_test.instance(Path(directory))
        shutil.copyfile(
            SCRIPTS.parent / "templates" / "packs" / "software" / "adapters" / "github.json",
            root / "catalog" / "adapters" / "github.json",
        )
        quiet(profiles.command_new, root, "alpha", "Alpha Corp", "company", "A forensic investigation firm")
        alpha = root / "profiles" / "alpha"
        try:
            scout.discover(alpha, search=fake_search)
            raise AssertionError("no tags, no discovery")
        except scout.rc.RcError as error:
            assert "no interest tags" in str(error)
        quiet(tags.command_add, alpha, "Japanese OCR")
        quiet(tags.command_add, alpha, "cross-encoder reranking")

        summary = quiet(scout.discover, alpha, "2026-09-18", search=fake_search)
        # Per tag: new repos, established active repos, newest arXiv papers, recent OpenAlex works.
        assert len(CALLS) == 8, CALLS
        new, active, arxiv, works = CALLS[:4]
        assert new == ("github", "Japanese OCR", {"created": "2026-09-18", "sort": "stars"}, None), new
        assert active == ("github", "Japanese OCR", {"minStars": "50", "sort": "stars"}, "2026-09-18"), active
        assert (
            arxiv[0] == "feed"
            and "export.arxiv.org/api/query" in arxiv[1]
            and "Japanese+OCR" in arxiv[1]
            and "submittedDate" in arxiv[1]
        )
        assert works == ("openalex", '"Japanese OCR"', {}, "2026-09-18"), "a tag is searched as a phrase"
        assert summary["failures"] == [
            "openalex for 'Japanese OCR': openalex: HTTP 429",
            "openalex for 'cross-encoder reranking': openalex: HTTP 429",
        ]

        found = json.loads((alpha / "scout" / "candidates" / f"{summary['stamp']}.json").read_text(encoding="utf-8"))[
            "candidates"
        ]
        by_title = {item["title"]: item for item in found}
        shared = by_title["acme/ocr-kit"]
        assert shared["tags"] == ["Japanese OCR", "cross-encoder reranking"] and shared["sources"] == ["github-new"], (
            shared
        )
        assert [item["title"] for item in found[:2]] == ["big/reranker", "acme/ocr-kit"], (
            "most tags first, then most stars"
        )
        assert shared["licence"] == {"spdx": "MIT", "class": "permissive", "usable": True, "reason": ""}
        assert (
            not by_title["acme/gpl-tool"]["licence"]["usable"]
            and by_title["acme/gpl-tool"]["licence"]["class"] == "copyleft"
        )
        assert (
            by_title["big/reranker"]["licence"]["class"] == "unknown"
            and by_title["big/reranker"]["kind"] == "repository"
        )
        assert sum(item["kind"] == "paper" for item in found) == 2 and summary["new"] == len(found) == 5

        # The seen-list: a second run surfaces nothing it already saw, and starts from the last discovery.
        seen = json.loads((alpha / "scout" / "seen.json").read_text(encoding="utf-8"))
        assert set(seen) == {item["key"] for item in found} and all(
            entry["status"] == "candidate" for entry in seen.values()
        )
        CALLS.clear()
        again = quiet(scout.discover, alpha, search=fake_search)
        assert again["since"] == scout.datetime.date.today().isoformat(), again
        assert again["new"] == 2 and again["stamp"] != summary["stamp"], "only the arXiv papers with new ids are new"
        assert len(list((alpha / "scout" / "candidates").glob("*.json"))) == 2

        # One tag only, and a source whose adapter is not enabled is skipped, not failed.
        (root / "catalog" / "adapters" / "github.json").unlink()
        CALLS.clear()
        only = quiet(scout.discover, alpha, "2026-10-01", ["japanese ocr"], search=fake_search)
        assert {call[0] for call in CALLS} == {"feed", "openalex"} and only["tags"] == ["Japanese OCR"], CALLS
        assert set(only["sourcesSkipped"]) == {"github-new", "github-active"} and len(only["failures"]) == 1
        assert profiles.meta_problems(tags.load(alpha), "alpha") == []
