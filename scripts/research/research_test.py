#!/usr/bin/env python3
"""Test the research pipeline end to end with fake roles and fake web pages: briefs are checked before a run,
sources merge across researchers and are stored, quotes are verified against stored text, a reply citing an
unknown or refuted claim gets one retry, reviews are anonymous, contested claims surface, the handoff is a CC
task plan, and runs resume and restart from a stage."""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent / "runner"), str(HERE.parent / "ingest"), str(HERE.parent / "sources")]
import extract  # noqa: E402
import ingest  # noqa: E402
import kit  # noqa: E402
import providers  # noqa: E402
import rc  # noqa: E402
import research  # noqa: E402
import sources_test  # noqa: E402  (its fixture transport answers the adapter searches)

PAPER = "https://example.org/paper"
BLOG = "https://www.example.org/paper/"  # the same page as PAPER once canonical
DEAD = "https://dead.example.org/post"
EXTRA = "https://extra.example.org/post"  # past the source limit of 2
RECORD = "https://doi.org/10.5555/WT.2025.1"  # an included OpenAlex record; it never counts against the limit
PLAN = {
    "horizon": "near",
    "hypotheses": [{"id": "H1", "statement": "Hybrid retrieval gives the best recall", "questions": ["Q1"]}],
    "exclusions": [{"id": "X1", "text": "Published before 2025", "from": "Scope"}],
    "avenues": [
        {"adapter": "openalex", "query": "hybrid retrieval recall", "filters": {"type": "article"}, "since": "2024-01-01",
         "stance": "support", "hypothesis": "H1", "questions": ["Q1"], "why": "measured results"},
        {"adapter": "crossref", "query": "hybrid retrieval failure", "stance": "disconfirm", "hypothesis": "H1",
         "questions": ["Q1"], "why": "find where hybrid loses"},
        {"adapter": "feed", "query": "https://agency.example.org/feed", "filters": {"evidenceType": "official-statistics"},
         "stance": "explore", "questions": ["Q1"], "why": "official numbers"},
        {"adapter": "gdelt", "query": "short", "stance": "explore", "questions": ["Q1"], "why": "news"},
        {"adapter": "web", "query": "hybrid retrieval production", "stance": "explore", "questions": ["Q1"], "why": "engineering blogs"},
    ],
}
PAGE = "Hybrid retrieval combines lexical and dense signals and improves recall on every benchmark we tried in production."
CALLS: list[str] = []
SEEN_PROMPTS: dict[str, str] = {}


def fake_page(url: str):
    if "dead" in url:
        raise extract.Skip("HTTP 404")
    return f"{ingest.url_slug(url)}.md", f"Source: {url}\n\n# Paper\n\n{PAGE}\n", "pandoc", PAGE.encode()


def block(data) -> str:
    return "Done.\n\n```json\n" + json.dumps(data) + "\n```"


def fake_run(role, prompt, cwd, log, timeout=0, on_say=None, shared=None):
    role_id = role["id"]
    CALLS.append(role_id)
    SEEN_PROMPTS[role_id] = prompt
    retry = "previous reply was rejected" in prompt
    if role_id == "source-planner":
        if retry:
            return block(PLAN)
        # The first plan only looks for support: no disconfirming avenue, so it is rejected.
        return block({**PLAN, "avenues": [avenue for avenue in PLAN["avenues"] if avenue["stance"] != "disconfirm"]})
    if role_id == "screener":
        candidates = [json.loads(line) for line in prompt.split("# Candidates, one JSON object per line\n\n", 1)[1].splitlines() if line.strip()]
        return block({"decisions": [
            {"id": item["id"], "decision": "exclude", "criterion": "X1", "reason": "an older release"} if "2024" in item["url"]
            else {"id": item["id"], "decision": "include", "questions": ["Q1"], "reason": "bears on recall"}
            for item in candidates]})
    if role_id == "researcher-claude":
        return block({"sources": [{"ref": "S1", "url": PAPER, "title": "Paper | Site", "published": "2026-01-01", "kind": "paper"}],
                      "claims": [{"text": "Hybrid retrieval improves recall.", "source": "S1", "questions": ["Q1"], "type": "benchmark",
                                  "quote": "improves recall on every benchmark we tried in production"},
                                 {"text": "Hybrid retrieval is production ready.", "source": "S1", "questions": ["Q1"],
                                  "quote": "a sentence that is nowhere on the page at all, really"}]})
    if role_id == "researcher-gpt":
        # The first reply is malformed (a claim that is a bare string): a wrong shape is retried like a wrong answer.
        malformed = [] if retry else ["dense is better"]
        # Three web sources against a limit of 2 (EXTRA is dropped) plus an included record, which does not count.
        return block({"sources": [{"ref": "A", "url": BLOG, "title": "Same paper", "kind": "blog"},
                                  {"ref": "B", "url": DEAD, "title": "Dead post", "kind": "forum"},
                                  {"ref": "C", "url": EXTRA, "title": "Over the limit", "kind": "blog"},
                                  {"ref": "R", "url": RECORD, "title": "Productivity", "kind": "paper"}],
                      "claims": [{"text": "Dense retrieval alone is always better.", "source": "B", "questions": ["Q1"],
                                  "quote": "dense always wins"},
                                 {"text": "A claim on a source past the limit.", "source": "C", "questions": ["Q1"],
                                  "quote": "this source is dropped with its claim"},
                                 {"text": "Output per hour rose by 7 percent.", "source": "R", "questions": ["Q1"],
                                  "quote": "Output per hour rose by 7 percent"}, *malformed]})
    if role_id == "analyst":
        cite = "C99" if not retry else "C2"
        python = "```python\nprint('a code sample before the JSON block')\n```\n\n"
        return f"## Summary\n\nHybrid wins.\n\n{python}## Q1: Which retrieval?\n\nHybrid [{cite}]. Not dense [C1; C3].\n\n" + block(
            {"ideas": [{"id": "I1", "name": "Hybrid retrieval", "summary": "BM25 plus dense.", "claims": ["C1"]},
                       {"id": "I2", "name": "Dense only", "summary": "Embeddings only.", "claims": ["C3"]}]})
    if role_id.startswith("sceptic-"):
        refute = role_id == "sceptic-grok"
        return block({"claims": [{"claim": "C1", "verdict": "HOLDS", "reason": "on the page"},
                                 {"claim": "C2", "verdict": "REFUTED" if refute else "WEAK", "reason": "not on the page"},
                                 {"claim": "C3", "verdict": "UNSUPPORTED", "reason": "page not stored"}], "analysis": []})
    if role_id == "judge":
        return block({"claims": [{"claim": "C1", "verdict": "HOLDS", "reason": "all agree"},
                                 {"claim": "C2", "verdict": "WEAK", "reason": "kept as weak"},
                                 {"claim": "C3", "verdict": "UNSUPPORTED", "reason": "no page"}],
                      "ideas": [{"idea": "I1", "verdict": "SURVIVES", "reason": "C1 holds"},
                                {"idea": "I2", "verdict": "FALLS", "reason": "C3 unsupported"}]})
    if role_id == "applier":
        return block({"fits": [{"idea": "I1", "ring": "TRIAL", "sources": ["git-api"], "replaces": "keyword | search", "effort": "M",
                                "risks": "embedding cost", "rationale": "Recall matters for us [C1].", "nextStep": "Shadow-run it."}]})
    if role_id == "reporter":
        cite = "[C1, C3]" if not retry else "the dense-only claim"
        return f"# Retrieval\n\n## TL;DR\n\n- Hybrid [C1].\n\n## Q1: Which retrieval?\n\nHybrid [C1], weakly [C2]; not {cite}.\n"
    raise AssertionError(f"unexpected role {role_id}")


def make_instance(base: Path) -> Path:
    root = base / "rc"
    (root / "catalog").mkdir(parents=True)
    shutil.copytree(REPO / "templates" / "agents", root / "catalog" / "agents")
    shutil.copytree(REPO / "templates" / "adapters", root / "catalog" / "adapters", copy_function=shutil.copyfile)
    shutil.copytree(REPO / ".agents", root / ".agents")
    shutil.copytree(REPO / "templates", root / "templates")
    settings = json.loads((REPO / "templates" / "research-center.json").read_text())
    settings["research"]["maxSourcesPerResearcher"] = 2
    (root / "research-center.json").write_text(json.dumps({**settings, "name": "test"}))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    # An ingested repo read from a local path: handoffs must name its remote, not the path.
    rc.write_json(root / "catalog" / "sources" / "git-api.json", {"schemaVersion": 1, "id": "git-api", "kind": "git",
                  "locators": ["/home/me/api"], "origin": "user", "note": "our API"})
    rc.write_json(root / "sources" / "git-api" / "manifest.json", {"id": "git-api", "kind": "git", "locators": ["/home/me/api"],
                  "remote": "https://github.com/acme/api.git", "files": {}, "skipped": []})
    return root


def quiet(function, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


def write_brief(root: Path) -> None:
    quiet(research.command_new, root, argparse.Namespace(topic="retrieval", title="Retrieval for our search"))
    path = root / "research" / "retrieval" / "brief.md"
    try:
        quiet(research.command_accept, root, argparse.Namespace(topic="retrieval"))
        raise AssertionError("a brief with placeholders must not be accepted")
    except rc.RcError as error:
        assert "placeholder" in str(error)
    filled = {
        "Topic": "Which retrieval to use for product search.",
        "Questions": "- Q1: Which retrieval approach gives the best recall for us?",
        "Scope": "Lexical, dense and hybrid retrieval, 2024 to 2026.",
        "Out of scope": "Rerankers.",
        "Our needs": "No profile.",
        "Success criteria": "A choice between the approaches.",
        "Source preferences": "Papers and engineering blogs.",
    }
    text = path.read_text().split("\n## ")[0]
    text += "".join(f"\n## {name}\n\n{body}\n" for name, body in filled.items())
    path.write_text(text)
    try:
        research.run_research(root, "retrieval", None, None)
        raise AssertionError("a draft brief must not run")
    except rc.RcError as error:
        assert "draft" in str(error)
    quiet(research.command_accept, root, argparse.Namespace(topic="retrieval"))
    assert "Status: accepted" in path.read_text()


def main() -> int:
    providers.run = fake_run
    ingest.url_document = fake_page
    ingest.guard = lambda root, lookup=None: None
    kit.TRANSPORT = sources_test.transport

    assert research.quote_found("recall on every benchmark we tried in production", PAGE)
    assert not research.quote_found("never said anything like this at all", PAGE)
    assert research.quote_found("lexical and dense signals and improves recall on every", "x " + PAGE.replace(" and ", "\nand "))
    assert not research.quote_found("tried in production", PAGE), "a quote shorter than six words never verifies"
    assert not research.quote_found("ok", "look at this"), "whole words only"
    seven = "The hybrid model improved exact match by 7 points over the dense baseline on all three of our internal benchmarks"
    assert research.quote_found(seven, "Intro. " + seven + " More.")
    assert not research.quote_found(seven, seven.replace(" 7 ", " 2 ")), "a changed number never verifies"
    negated = "Hybrid retrieval does not improve recall on the benchmarks we ran in production this year at all"
    assert not research.quote_found(negated, negated.replace(" not ", " ")), "a lost negation never verifies"
    assert research.claim_refs("Yes [C3, C7] and [C1; C2] and [C9].") == ["C3", "C7", "C1", "C2", "C9"]
    assert rc.extract_json('Code:\n```python\nx = 1\n```\n\nData:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert rc.extract_json('```\n{"b": 2}\n```\n\n```mermaid\ngraph TD\n```') == {"b": 2}
    assert research.source_key(PAPER) == research.source_key(BLOG)
    assert research.source_key(RECORD) == "doi:10.5555/wt.2025.1"
    assert research.source_key("https://x.org/item?id=1") != research.source_key("https://x.org/item?id=2"), "queries stay apart"
    adapters = {path.stem: json.loads(path.read_text()) for path in (REPO / "templates" / "adapters").glob("*.json")}
    assert research.plan_problems(PLAN, {"Q1"}, adapters) == []
    problems = " ".join(research.plan_problems({**PLAN, "avenues": [{**avenue, "filters": {"bogus": "1"}} if avenue["adapter"] == "openalex"
                                                                    else avenue for avenue in PLAN["avenues"] if avenue["adapter"] != "feed"]
                                                } | {"horizon": "soon", "exclusions": [{"id": "X0", "text": "reserved", "from": "Nowhere"}]},
                                                {"Q1", "Q2"}, adapters))
    for expected in ("horizon", "X0 is reserved", "brief section", "no filter", "no avenue serves Q2"):
        assert expected in problems, (expected, problems)
    web_only = {**PLAN, "avenues": [avenue for avenue in PLAN["avenues"] if avenue["adapter"] in ("web", "openalex", "crossref")]}
    assert "two families" in " ".join(research.plan_problems(web_only, {"Q1"}, adapters)), "scholarly alone is one family"

    with tempfile.TemporaryDirectory() as directory:
        root = make_instance(Path(directory))
        write_brief(root)
        quiet(research.run_research, root, "retrieval", None, None)
        topic = root / "research" / "retrieval"

        # Plan: the one-sided first plan is rejected; the stored plan carries the hypotheses and X0 + X1.
        assert CALLS.count("source-planner") == 2 and "H1 has no disconfirming avenue" in SEEN_PROMPTS["source-planner"]
        plan = json.loads((topic / "source-plan.json").read_text())
        assert [item["id"] for item in plan["exclusions"]] == ["X0", "X1"] and "| disconfirm H1 |" in (topic / "source-plan.md").read_text()

        # Search: every adapter avenue ran and was logged, the failing one included; the web avenue is not searched here.
        searches = json.loads((topic / "searches.json").read_text())
        assert [(entry["adapter"], entry["status"]) for entry in searches] == \
            [("openalex", "ok"), ("crossref", "ok"), ("feed", "ok"), ("gdelt", "error")], searches
        candidates = json.loads((topic / "candidates.json").read_text())
        assert candidates["identified"] == 6 and len(candidates["records"]) == 5, "the DOI found by openalex and crossref merges"

        # Screen: retracted records are excluded by the runner, the rest by the screener with a criterion; counts add up.
        screening = json.loads((topic / "screening.json").read_text())
        flow = screening["flow"]
        assert flow == {"identified": 6, "duplicates": 1, "screened": 5, "excluded": 3, "excludedBy": {"X1": 1, "retracted": 2},
                        "included": 2}, flow
        assert flow["screened"] == flow["excluded"] + flow["included"] and flow["identified"] == flow["screened"] + flow["duplicates"]
        assert all(row["criterion"] in ("X1", "retracted") for row in screening["records"] if row["decision"] == "exclude")
        assert CALLS.count("screener") == 1 and "R2" not in SEEN_PROMPTS["screener"].split("# Candidates")[1], "retracted records skip the screener"
        included = [row for row in screening["records"] if row["decision"] == "include"]
        record_text = (root / included[0]["stored"]).read_text()
        assert included[0]["stored"].startswith("sources/search-retrieval/") and "Output per hour rose by 7 percent." in record_text
        assert "## Excluded" in (topic / "screening.md").read_text()

        ledger = json.loads((topic / "claims.json").read_text())
        assert [source["url"] for source in ledger["sources"]] == [PAPER, DEAD, RECORD], "PAPER and BLOG merge into one source"
        assert ledger["sources"][0]["foundBy"] == ["researcher-claude", "researcher-gpt"]
        assert ledger["sources"][1]["stored"] is None and ledger["sources"][1]["fetch"].startswith("failed")
        assert ledger["sources"][2]["record"] == included[0]["id"] and ledger["sources"][2]["stored"] == included[0]["stored"]
        assert [claim["quoteVerified"] for claim in ledger["claims"]] == [True, False, False, True], \
            "the record's claim is checked against its stored abstract, not a download"
        stored = root / ledger["sources"][0]["stored"]
        assert stored.is_file() and PAGE in stored.read_text()
        assert json.loads((root / "catalog" / "sources" / "web-retrieval.json").read_text())["origin"] == "research:retrieval"

        assert CALLS.count("analyst") == 2 and CALLS.count("reporter") == 2, f"one retry each: {CALLS}"
        assert CALLS.count("researcher-gpt") == 2, f"a malformed reply is retried: {CALLS}"
        assert EXTRA not in json.dumps(ledger), "a source past the limit is dropped with its claim"
        assert "C99" in SEEN_PROMPTS["analyst"], "the retry names the problem"

        reviews = sorted(path.name for path in (topic / "critique").glob("*.json"))
        assert reviews == ["review-a.json", "review-b.json", "review-c.json"], reviews
        mapping = json.loads((root / ".rc-local" / "research" / "retrieval" / "reviewers.json").read_text())
        assert sorted(mapping.values()) == ["sceptic-claude", "sceptic-gpt", "sceptic-grok"]
        judge_prompt = SEEN_PROMPTS["judge"]
        assert "## Review A" in judge_prompt and "sceptic-" not in judge_prompt.split("# Task", 1)[1], "the judge sees labels only"

        judgement = json.loads((topic / "judgement.json").read_text())
        assert judgement["contested"] and judgement["contested"][0]["claim"] == "C2", judgement["contested"]

        fit = json.loads((topic / "fit.json").read_text())
        assert [item["idea"] for item in fit["fits"]] == ["I1"], "the idea that fell is not applied"
        handoff = (topic / "handoff.md").read_text()
        for heading in ("## Outcome", "## Work packages", "## Acceptance criteria", "## Lifecycle closure"):
            assert heading in handoff, heading
        assert "Lifecycle: active" in handoff and handoff.rstrip().endswith("Not closed.") and "Hybrid retrieval (TRIAL" in handoff
        assert "| git-api (https://github.com/acme/api.git) |" in handoff and "/home/me/api" not in handoff, handoff
        assert "keyword \\| search" in (topic / "fit.md").read_text(), "pipes in cells are escaped"

        report = (topic / "report.md").read_text()
        assert report.startswith("# Retrieval for our search") and "[C3]" not in report.split("## Evidence")[0]
        assert "## Evidence" in report and "| C1 | HOLDS | yes | [Paper \\| Site](" in report and "## Contested" in report
        assert "C3 (UNSUPPORTED)" in report and "## Handoff" in report
        assert "## How the sources were found" in report and "- Duplicates removed: 1" in report and "X1 (Published before 2025): 1" in report

        validator = __import__("importlib.util").util
        spec = validator.spec_from_file_location("validate_rc", REPO / "scripts" / "validate-research-center.py")
        module = validator.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.validate(root) == [], module.validate(root)

        # Resume: a finished run costs nothing; --from judge redoes judge, apply and report only.
        CALLS.clear()
        quiet(research.run_research, root, "retrieval", None, None)
        assert CALLS == [], CALLS
        quiet(research.run_research, root, "retrieval", "judge", None)
        assert CALLS == ["judge", "applier", "reporter", "reporter"], CALLS

        # A missing middle output redoes everything after it.
        CALLS.clear()
        (topic / "analysis.md").unlink()
        quiet(research.run_research, root, "retrieval", None, None)
        assert CALLS[0] == "analyst" and "source-planner" not in CALLS and CALLS[-1] == "reporter", CALLS

        # The budget stops a run; finished stages stay.
        CALLS.clear()
        try:
            quiet(research.run_research, root, "retrieval", "critique", 2)
            raise AssertionError("the budget must stop the run")
        except rc.BudgetExceeded:
            pass
        assert (topic / "analysis.md").is_file() and not (topic / "report.md").exists()
        # The sceptics that answered before the budget ran out are not paid for again.
        replies = root / ".rc-local" / "research" / "retrieval" / "replies"
        assert len(list((replies / "critique").glob("*.json"))) == 2, list(replies.rglob("*"))
        CALLS.clear()
        quiet(research.run_research, root, "retrieval", None, None)
        assert sum(call.startswith("sceptic-") for call in CALLS) == 1 and CALLS[-1] == "reporter", CALLS
        assert not any(replies.rglob("*.json")), "finished stages keep no replies"
    print("research test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
