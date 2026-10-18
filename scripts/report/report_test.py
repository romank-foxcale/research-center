#!/usr/bin/env python3
"""Test ./rc report: a fixture topic renders every section, with claim links, the hypothesis matrix ranked and
refuted rows struck out, and a living topic's history; text from the web stays text (no injected HTML, no
javascript: links); secrets are redacted; a topic whose stages have not run renders what exists; and the same
outputs give the same bytes. Without a topic: a dashboard of every topic, living first, linked both ways with
the topic pages beside it, showing the scope without its evidence paths."""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import report  # noqa: E402

SECRET = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
INJECTED = "<script>alert(1)</script>"
BRIEF = """# Which retrieval for product search?

Topic: retrieval
Status: living

## Topic

Retrieval.

## Questions

- Q1: Which retrieval approach gives the best recall for us?
- Q2: Which vendors offer it?
"""
REPORT = f"""# Which retrieval for product search?

Topic: retrieval · Date: 2026-10-16 · Claims: 3 · Sources: 2 · Version 2

## In plain words

**The short answer**: use hybrid search; it finds more of what matters.

## TL;DR

- Hybrid retrieval wins on recall [C1, C2]. <img src=x onerror=alert(1)>
- Assessment: shadow-run it first.

## Q1: Which retrieval approach gives the best recall for us?

Certainty: low. Hybrid [C1]; dense alone is refuted [C3].
"""


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def fixture(root: Path) -> Path:
    topic = root / "research" / "retrieval"
    write(root / "profile.json", {"id": "acme", "name": "Acme product scouting", "type": "company",
                                  "description": "", "tags": [{"tag": "search ranking"}, "e-commerce"]})
    write(topic / "brief.md", BRIEF)
    write(topic / "source-plan.json", {
        "hypotheses": [{"id": "H1", "statement": "Hybrid gives the best recall", "questions": ["Q1"]},
                       {"id": "H2", "statement": "Dense alone gives the best recall", "questions": ["Q1"]}],
        "noAlternatives": [{"question": "Q2", "why": "a list of vendors to compile"}]})
    write(topic / "screening.json", {
        "flow": {"identified": 40, "duplicates": 2, "citationIdentified": 10, "citationDuplicates": 1, "screened": 47,
                 "excluded": 44, "excludedBy": {"X0": 30, "X1": 14}, "included": 3},
        "criteria": [{"id": "X0", "text": "Bears on none of the brief's questions"}, {"id": "X1", "text": "Published before 2025"}]})
    write(topic / "claims.json", {
        "sources": [{"id": "S1", "url": "https://example.org/paper", "title": "Hybrid paper", "evidenceType": "peer-reviewed",
                     "reliability": "B", "published": "2026-01-01"},
                    {"id": "S2", "url": "javascript:alert(1)", "title": f"Vendor post {INJECTED}", "evidenceType": "vendor", "reliability": "D"}],
        "claims": [{"id": "C1", "text": "Hybrid retrieval improves recall.", "source": "S1", "quote": "improves recall on every benchmark",
                    "questions": ["Q1"], "quoteVerified": True},
                   {"id": "C2", "text": f"Our key {SECRET} leaked in a blog.", "source": "S1", "quote": "a quote here",
                    "questions": ["Q1"], "quoteVerified": True},
                   {"id": "C3", "text": f"Dense always wins {INJECTED}", "source": "S2", "quote": "dense always wins",
                    "questions": ["Q1"], "quoteVerified": False}]})
    write(topic / "ideas.json", {
        "ideas": [{"id": "I1", "name": "Hybrid retrieval", "summary": "BM25 plus dense.", "claims": ["C1"]},
                  {"id": "I2", "name": "Dense only", "summary": "Embeddings only.", "claims": ["C3"]}],
        "questions": [{"question": "Q1",
                       "assumptions": [{"id": "A1", "text": "Benchmarks predict our catalogue", "claims": ["C1"]}],
                       "ach": {"hypotheses": ["H1", "H2"],
                               "matrix": [{"claim": "C1", "ratings": {"H1": "C", "H2": "I"}},
                                          {"claim": "C2", "ratings": {"H1": "C", "H2": "N"}},
                                          {"claim": "C3", "ratings": {"H1": "I", "H2": "C"}}],
                               "untested": ["Learned sparse retrieval alone"]}}]})
    write(topic / "judgement.json", {
        "claims": [{"claim": "C1", "verdict": "HOLDS", "credibility": 2, "reason": "on the page"},
                   {"claim": "C2", "verdict": "WEAK", "credibility": 3, "reason": "one benchmark"},
                   {"claim": "C3", "verdict": "REFUTED", "credibility": 5, "reason": "not on the page"}],
        "ideas": [{"idea": "I1", "verdict": "SURVIVES", "reason": "C1 holds",
                   "history": [{"version": 1, "date": "2026-09-01", "verdict": "WEAKENED"}, {"version": 2, "date": "2026-10-16", "verdict": "SURVIVES"}]},
                  {"idea": "I2", "verdict": "FALLS", "reason": "C3 refuted"}],
        "assumptions": [{"assumption": "A1", "verdict": "WEAK", "reason": "untested on our catalogue"}],
        "answers": [{"question": "Q1", "certainty": "low",
                     "downgrades": [{"domain": "imprecision", "levels": 1, "reason": "one benchmark", "claims": ["C1"]}], "upgrades": []}],
        "contested": [{"claim": "C2", "refutedBy": ["Review b"]}], "notes": "Do not overstate C1."})
    write(topic / "fit.json", {"fits": [{"idea": "I1", "ring": "TRIAL", "replaces": "keyword search", "effort": "M", "risks": "embedding cost",
                                         "rationale": "Recall matters for us [C1].", "nextStep": "Shadow-run it.",
                                         "history": [{"version": 1, "date": "2026-09-01", "ring": "ASSESS"},
                                                     {"version": 2, "date": "2026-10-16", "ring": "TRIAL"}]}]})
    write(topic / "watch.json", {"cadence": "monthly", "cadenceDays": 30, "retireWhen": "we chose", "lastChecked": "2026-10-16",
                                 "lastChanged": "2026-10-16", "log": [{"date": "2026-09-01", "version": 1, "kind": "run"},
                                                                      {"date": "2026-10-16", "version": 2, "kind": "refresh", "material": True}]})
    write(topic / "delta" / "2026-10-16.json", {"stamp": "2026-10-16", "material": True, "summary": "a new trial weakened C1"})
    write(topic / "delta" / "2026-10-16-searches.json", {"searches": []})
    write(topic / "report.md", REPORT)
    return topic


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture(root)
        path = report.command_topic(root, "retrieval", None)
        assert path == root / ".rc-local" / "reports" / "retrieval.html", path
        page = path.read_text(encoding="utf-8")

        # Every section, in decision order.
        anchors = ["plain", "bottom-line", "ideas", "answers", "evidence", "hypotheses", "report", "claims", "sources", "history"]
        positions = [page.find(f'id="{anchor}"') for anchor in anchors]
        assert all(position > 0 for position in positions) and positions == sorted(positions), dict(zip(anchors, positions))
        assert "use hybrid search; it finds more of what matters." in page and "Bottom line, with its evidence" in page
        assert page.count("The short answer") == 1, "the plain summary is not repeated in the full report"
        assert "Acme product scouting" in page and "<title>Which retrieval for product search?</title>" in page

        # Text from the web stays text, links are http(s) only, secrets are redacted.
        assert page.count("<script>") == 1, "only the page's own script"
        assert "<img" not in page and "&lt;img src=x onerror=alert(1)&gt;" in page
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
        assert 'href="javascript:' not in page and "Vendor post" in page
        assert SECRET not in page, "a secret in the outputs is redacted from the page"

        # Claims cited anywhere link to the appendix, with the claim as tooltip.
        assert re.search(r'<a class="cref cv-holds" href="#C1" title="Hybrid retrieval improves recall. \(HOLDS\)">C1</a>', page)
        assert '<tr id="C3" data-verdict="REFUTED">' in page and "quote not found on the stored page" in page
        assert "contested</span>" in page

        # Ideas by ring then verdict; ring and verdict history; certainty and its downgrades.
        assert page.find("Hybrid retrieval</h3>") < page.find("Dense only</h3>")
        assert "ASSESS (2026-09-01) → TRIAL (2026-10-16)" in page and "WEAKENED (2026-09-01) → SURVIVES (2026-10-16)" in page
        assert "certainty-low" in page and "−1 imprecision" in page and "Do not overstate" in page

        # The matrix: H1 ranks first (C3, which is inconsistent with it, was refuted); the refuted row is struck out.
        ranking = page[page.find('<ol class="ranking">'):]
        assert ranking.find("<b>H1</b>") < ranking.find("<b>H2</b>")
        assert '<tr class="out"><th scope="row">[<a class="cref cv-refuted" href="#C3"' in page
        assert "Learned sparse retrieval alone" in page and "a list of vendors to compile" in page

        # Screening and history.
        assert "Published before 2025" in page and ">47<" in page
        assert "a new trial weakened C1" in page and "-searches" not in page

        # The same outputs give the same bytes.
        assert report.render_topic(root, "retrieval") == report.render_topic(root, "retrieval")

        # A topic whose stages have not run renders what exists and says what is missing.
        partial = root / "research" / "early"
        partial.mkdir(parents=True)
        (partial / "brief.md").write_text(BRIEF.replace("Status: living", "Status: accepted"), encoding="utf-8")
        early = report.render_topic(root, "early")
        assert "Not produced yet: the report stage" in early and "Not produced yet: the analyze stage" in early
        assert 'id="claims"' not in early and "Not judged yet." in early

        # The dashboard: every topic, living first, each linked to its page beside it, which links back.
        (root / "scope.md").write_text("# Acme\n\nProfile: acme\nStatus: accepted\n\n## Who\n\nAcme sells parts online "
                                       "[acme.example/about].\n\nSecond paragraph.\n", encoding="utf-8")
        index = report.command_dashboard(root, None)
        assert index == root / ".rc-local" / "reports" / "index.html"
        board = index.read_text(encoding="utf-8")
        assert "<title>Acme product scouting</title>" in board and "2 topics, 1 living" in board
        assert board.find('href="retrieval.html"') < board.find('href="early.html"'), "living topics first"
        assert "1 TRIAL" in board and "Hybrid retrieval" in board and "Dense only" not in board, "leading ideas are ADOPT or TRIAL"
        assert "certainty-low" in board and "not run" in board and "3 claims, 2 sources" in board
        assert "search ranking</span>" in board and "e-commerce</span>" in board and "status-company" in board
        assert "Acme sells parts online." in board and "acme.example" not in board and "Second paragraph" not in board
        assert "<script>" not in board
        beside = (index.parent / "retrieval.html").read_text(encoding="utf-8")
        assert '<a href="index.html">&larr; All topics</a>' in beside and (index.parent / "early.html").is_file()
        assert 'href="index.html"' not in page, "a single topic's page has no dashboard to link back to"
        # A share publishes the dashboard with the pages beside it, and remembers its link so the next share updates it.
        shared = report.manifest(root, None, index)
        assert shared["page"] == str(index.parent / "share" / "index.html") and shared["sharedAt"] is None
        assert shared["title"] == "Acme product scouting"
        content = Path(shared["page"]).read_text(encoding="utf-8")
        assert content.startswith("<title>Acme product scouting</title>") and "<!doctype" not in content and "<body" not in content, \
            "an artifact wraps the page it publishes in its own document"
        assert all(Path(path).read_text(encoding="utf-8").startswith("<!doctype html>") for path in shared["files"].values()), \
            "pages published beside it are served as they are, so they are whole documents"
        assert 'name="claude:viewport-fit-sides"' in content and "max(16px,env(safe-area-inset-left" in content
        assert set(shared["files"]) == {"retrieval.html", "early.html"} and all(Path(path).is_file() for path in shared["files"].values())
        report.remember_share(index.parent, "index", "https://claude.ai/code/artifact/0b1c")
        assert report.manifest(root, None, index)["sharedAt"]["url"] == "https://claude.ai/code/artifact/0b1c"
        assert report.manifest(root, "retrieval", path)["files"] == {} and report.manifest(root, "retrieval", path)["sharedAt"] is None
        try:
            report.remember_share(index.parent, "index", "https://example.org/x")
            raise AssertionError("only claude.ai artifact links are recorded")
        except report.rc.RcError as error:
            assert "not a claude.ai artifact link" in str(error)

        (root / "research" / "index").mkdir()
        (root / "research" / "index" / "brief.md").write_text(BRIEF, encoding="utf-8")
        try:
            report.command_dashboard(root, None)
            raise AssertionError("a topic named index must not overwrite the dashboard")
        except report.rc.RcError as error:
            assert "collides" in str(error)

        # A topic that does not exist is an error, not an empty page.
        try:
            report.render_topic(root, "nothing")
            raise AssertionError("a missing topic must fail")
        except report.rc.RcError as error:
            assert "no topic nothing" in str(error)
    print("report test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
