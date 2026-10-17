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
import living  # noqa: E402
import research  # noqa: E402
import sources_test  # noqa: E402  (its fixture transport answers the adapter searches)

PAPER = "https://example.org/paper"
BLOG = "https://www.example.org/paper/"  # the same page as PAPER once canonical
DEAD = "https://dead.example.org/post"
EXTRA = "https://extra.example.org/post"  # past the source limit of 2
RECORD = "https://doi.org/10.5555/WT.2025.1"  # an included OpenAlex record; it never counts against the limit
PLAN = {
    "horizon": "near",
    "hypotheses": [{"id": "H1", "statement": "Hybrid retrieval gives the best recall", "questions": ["Q1"]},
                   {"id": "H2", "statement": "Dense retrieval alone gives the best recall", "questions": ["Q1"]}],
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
        {"adapter": "web", "query": "dense retrieval worse than BM25", "stance": "disconfirm", "hypothesis": "H2", "questions": ["Q1"],
         "why": "find where dense alone loses"},
    ],
}
PAGE = "Hybrid retrieval combines lexical and dense signals and improves recall on every benchmark we tried in production."
NEW = "https://doi.org/10.5555/w700"  # the record a refresh finds: hybrid retrieval loses in a new trial
CALLS: list[str] = []
SEEN_PROMPTS: dict[str, str] = {}
PHASE = {"refresh": False}  # after the refresh finds NEW, the analysis cites C5 and the judge weakens C1


def fake_page(url: str):
    if "dead" in url:
        raise extract.Skip("HTTP 404")
    page = PHASE.get("page") or PAGE
    return f"{ingest.url_slug(url)}.md", f"Source: {url}\n\n# Paper\n\n{page}\n", "markdownify", page.encode()


def graded(evidence: str, grade: str) -> dict[str, str]:
    return {"evidenceType": evidence, "reliability": grade, "reliabilityReason": f"graded {grade} as {evidence}"}


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
    if role_id.startswith("researcher-") and "A refresh of research" in prompt:
        assert NEW in prompt and "Do not search the web" in prompt, "a refresh shows only the new records"
        quote = "Hybrid retrieval lost recall to dense retrieval in our new production trial" if role_id == "researcher-claude" \
            else "lost recall to dense retrieval in our new production trial"
        return block({"sources": [{"ref": "N", "url": NEW, "title": "New trial", **graded("peer-reviewed", "B")}],
                      "claims": [{"text": f"In a new trial hybrid lost recall ({role_id}).", "source": "N", "questions": ["Q1"], "quote": quote}]})
    if role_id == "researcher-claude":
        return block({"sources": [{"ref": "S1", "url": PAPER, "title": "Paper | Site", "published": "2026-01-01", **graded("peer-reviewed", "B")}],
                      "claims": [{"text": "Hybrid retrieval improves recall.", "source": "S1", "questions": ["Q1"], "type": "benchmark",
                                  "quote": "improves recall on every benchmark we tried in production"},
                                 {"text": "Hybrid retrieval is production ready.", "source": "S1", "questions": ["Q1"],
                                  "quote": "a sentence that is nowhere on the page at all, really",
                                  "via": "the authors' own benchmark table, https://www.example.org/paper/"}]})
    if role_id == "researcher-sonnet":
        # The first reply is malformed (a claim that is a bare string): a wrong shape is retried like a wrong answer.
        malformed = [] if retry else ["dense is better"]
        # Three web sources against a limit of 2 (EXTRA is dropped) plus an included record, which does not count.
        return block({"sources": [{"ref": "A", "url": BLOG, "title": "Same paper", **graded("commentary", "D")},
                                  {"ref": "B", "url": DEAD, "title": "Dead post", **graded("forum", "A")},
                                  {"ref": "C", "url": EXTRA, "title": "Over the limit", **graded("commentary", "D")},
                                  {"ref": "R", "url": RECORD, "title": "Productivity", **graded("unknown", "C")}],
                      "claims": [{"text": "Dense retrieval alone is always better.", "source": "B", "questions": ["Q1"],
                                  "quote": "dense always wins", "via": "a vendor whitepaper"},
                                 {"text": "A claim on a source past the limit.", "source": "C", "questions": ["Q1"],
                                  "quote": "this source is dropped with its claim"},
                                 {"text": "Output per hour rose by 7 percent.", "source": "R", "questions": ["Q1"],
                                  "quote": "Output per hour rose by 7 percent"}, *malformed]})
    if role_id == "analyst":
        cite = "C99" if not retry else "C2"
        python = "```python\nprint('a code sample before the JSON block')\n```\n\n"
        update = " A new trial disagrees [C5]." if PHASE["refresh"] else ""
        return f"## Summary\n\nHybrid wins.\n\n{python}## Q1: Which retrieval?\n\nHybrid [{cite}]. Not dense [C1; C3].{update}\n\n" + block(
            {"ideas": [{"id": "I1", "name": "Hybrid retrieval", "summary": "BM25 plus dense.", "claims": ["C1"]},
                       {"id": "I2", "name": "Dense only", "summary": "Embeddings only.", "claims": ["C3"]}],
             "questions": [{"question": "Q1",
                            "assumptions": [{"id": "A1", "text": "Recall on public benchmarks predicts recall on our catalogue", "claims": ["C1"]}],
                            "ach": {"hypotheses": ["H1", "H2"],
                                    "matrix": [{"claim": "C1", "ratings": {"H1": "C", "H2": "I"}},
                                               {"claim": "C3", "ratings": {"H1": "I", "H2": "C"}},
                                               {"claim": "C2", "ratings": {"H1": "C", "H2": "N"}}],
                                    "untested": ["Learned sparse retrieval alone"]}}]})
    if role_id.startswith("sceptic-"):
        refute = role_id == "sceptic-sonnet"
        update = [{"claim": "C5", "verdict": "HOLDS", "reason": "in the new trial's abstract"}] if PHASE["refresh"] else []
        return block({"claims": [{"claim": "C1", "verdict": "HOLDS", "reason": "on the page"},
                                 {"claim": "C2", "verdict": "REFUTED" if refute else "WEAK", "reason": "not on the page"},
                                 {"claim": "C3", "verdict": "UNSUPPORTED", "reason": "page not stored"}, *update],
                      "assumptions": [{"assumption": "A1", "verdict": "WEAK", "reason": "our catalogue is not a public benchmark"}],
                      "analysis": []})
    if role_id == "judge":
        refreshed = PHASE["refresh"]
        update = [{"claim": "C5", "verdict": "HOLDS", "credibility": 2, "reason": "the new trial"}] if refreshed else []
        return block({"claims": [{"claim": "C1", "verdict": "WEAK" if refreshed else "HOLDS", "credibility": 3 if refreshed else 2, "reason": "a new trial disagrees" if refreshed else "all agree"},
                                 {"claim": "C2", "verdict": "WEAK", "credibility": 3, "reason": "kept as weak"},
                                 {"claim": "C3", "verdict": "UNSUPPORTED", "credibility": 6, "reason": "no page"}, *update],
                      "ideas": [{"idea": "I1", "verdict": "SURVIVES", "reason": "C1 holds"},
                                {"idea": "I2", "verdict": "FALLS", "reason": "C3 unsupported"}],
                      "assumptions": [{"assumption": "A1", "verdict": "WEAK", "reason": "untested on our catalogue"}],
                      "answers": [{"question": "Q1", "certainty": "low",
                                   "downgrades": [{"domain": "imprecision", "levels": 1, "reason": "one benchmark", "claims": ["C1"]},
                                                  {"domain": "one-sided", "levels": 1, "reason": "only the authors measured it"}]}]})
    if role_id == "applier":
        return block({"fits": [{"idea": "I1", "ring": "TRIAL", "sources": ["git-api"], "replaces": "keyword | search", "effort": "M",
                                "risks": "embedding cost", "rationale": "Recall matters for us [C1].", "nextStep": "Shadow-run it."}]})
    if role_id == "reporter":
        cite = "[C1, C3]" if not retry else "the dense-only claim"
        hedge = "Hybrid is probably better." if not retry else "Assessment: hybrid is likely the better default for us."
        # The first reply has no plain summary; the retry has one, and a bold label on its own line, which states nothing.
        plain = "" if not retry else ("## In plain words\n\n**The short answer**: use hybrid search.\n\n"
                                      "**How sure we are**: low; one benchmark.\n\n")
        label = "" if not retry else "**Benchmarks**\n\n"
        return (f"# Retrieval\n\n{plain}## TL;DR\n\n- Hybrid [C1].\n\n## Q1: Which retrieval?\n\nCertainty: low, one benchmark.\n\n"
                f"{label}Hybrid [C1], weakly [C2]; not {cite}.\n\n{hedge}\n")
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
        "Living": "Cadence: monthly\nRetire when: we have chosen a retrieval approach.",
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


def test_living(root: Path, topic: Path) -> None:
    """A topic with a cadence becomes living; refresh costs nothing when nothing is new, and with one new contradicting
    record it adds the next claim ids, re-derives the conclusions, and flags the flipped verdict for review."""
    assert "Status: living" in (topic / "brief.md").read_text(encoding="utf-8")
    watch = json.loads((topic / "watch.json").read_text(encoding="utf-8"))
    assert watch["cadenceDays"] == 30 and watch["retireWhen"] == "we have chosen a retrieval approach."
    assert [query["adapter"] for query in watch["queries"]] == ["openalex", "crossref", "feed", "gdelt"], "web avenues are not watched"
    version = watch["version"]
    assert f"· Version {version} · Checked {rc.today()}" in (topic / "report.md").read_text(encoding="utf-8")
    claims_before = json.loads((topic / "claims.json").read_text(encoding="utf-8"))["claims"]
    stored_before = [row["stored"] for row in json.loads((topic / "screening.json").read_text(encoding="utf-8"))["records"] if row.get("stored")]

    # Nothing new: no agent call, no new version.
    CALLS.clear()
    delta = quiet(living.refresh, root, "retrieval")
    assert CALLS == [] and not delta["material"] and delta["summary"] == "no material change: nothing new was found", (CALLS, delta)
    first = topic / "delta" / f"{rc.today()}.md"
    assert first.is_file() and "No material change: nothing new was found." in first.read_text(encoding="utf-8")
    assert json.loads((topic / "watch.json").read_text(encoding="utf-8"))["version"] == version
    searches = json.loads((topic / "delta" / f"{rc.today()}-searches.json").read_text(encoding="utf-8"))
    assert {entry["since"] for entry in searches} == {rc.today()}, "saved queries search since the last check"

    # One new record that contradicts the report.
    sources_test.ROUTES.insert(0, ("search=hybrid", "openalex-refresh.json", "application/json"))
    PHASE["refresh"] = True
    # The budget stops it during collect: the screening is kept and the refresh resumes where it stopped.
    CALLS.clear()
    raises(rc.BudgetExceeded, living.refresh, root, "retrieval", 2)
    assert CALLS.count("screener") == 1 and json.loads((topic / "watch.json").read_text(encoding="utf-8"))["pending"]["step"] == "screened"
    CALLS.clear()
    delta = quiet(living.refresh, root, "retrieval")
    assert "screener" not in CALLS and sum(call.startswith("researcher-") for call in CALLS) == 1 and CALLS[-1] == "reporter", \
        f"the screening and the researcher that answered are not paid for again: {CALLS}"
    assert "# Previous version" in SEEN_PROMPTS["analyst"] and "I1: Hybrid retrieval" in SEEN_PROMPTS["analyst"]
    claims = json.loads((topic / "claims.json").read_text(encoding="utf-8"))["claims"]
    assert claims[:4] == claims_before, "existing claims keep their ids and text"
    assert [(claim["id"], claim["quoteVerified"], claim["addedIn"]) for claim in claims[4:]] == [("C5", True, version + 1), ("C6", True, version + 1)]
    judgement = json.loads((topic / "judgement.json").read_text(encoding="utf-8"))
    first_claim = next(item for item in judgement["claims"] if item["claim"] == "C1")
    assert [(entry["version"], entry["verdict"]) for entry in first_claim["history"]][-2:] == [(version, "HOLDS"), (version + 1, "WEAK")]
    fit = json.loads((topic / "fit.json").read_text(encoding="utf-8"))["fits"][0]
    assert [entry["ring"] for entry in fit["history"]][-2:] == ["TRIAL", "TRIAL"]
    assert delta["material"] and delta["flips"] == [{"claim": "C1", "from": "HOLDS", "to": "WEAK"}] and not delta["moves"]
    second = (topic / "delta" / f"{rc.today()}-2.md").read_text(encoding="utf-8")
    assert "## Needs your review" in second and "- C1: HOLDS → WEAK" in second and "| C5 |" in second
    watch = json.loads((topic / "watch.json").read_text(encoding="utf-8"))
    assert watch["version"] == version + 1 and watch["pending"] is None and watch["lastChanged"] == rc.today()
    assert f"· Version {version + 1} ·" in (topic / "report.md").read_text(encoding="utf-8")
    screening = json.loads((topic / "screening.json").read_text(encoding="utf-8"))
    added = [row for row in screening["records"] if row.get("addedAt")]
    assert [(row["url"], row["decision"]) for row in added] == [(NEW, "include")] and (root / added[0]["stored"]).is_file()
    assert all((root / path).is_file() for path in stored_before), "a refresh appends stored records, never replaces them"
    validator = __import__("importlib.util").util
    spec = validator.spec_from_file_location("validate_rc", REPO / "scripts" / "validate-research-center.py")
    module = validator.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.validate(root) == [], module.validate(root)

    # Drift: the paper's page changed after its half-life passed; the claim C1 rests on is marked drifted and re-critiqued.
    PHASE["page"] = "Hybrid retrieval was evaluated; results are now in the appendix and vary by benchmark and by year."
    led = json.loads((topic / "claims.json").read_text(encoding="utf-8"))
    led["sources"][0]["checkedAt"] = "2020-01-01"
    rc.write_json(topic / "claims.json", led)
    CALLS.clear()
    delta = quiet(living.refresh, root, "retrieval")
    first_claim = next(claim for claim in json.loads((topic / "claims.json").read_text(encoding="utf-8"))["claims"] if claim["id"] == "C1")
    assert first_claim["drifted"]["reason"] == "the page no longer contains the quote" and not first_claim["quoteVerified"]
    assert delta["material"] and [claim["id"] for claim in delta["drifted"]] == ["C1"] and CALLS.count("judge") == 1, (delta["summary"], CALLS)
    assert sum(call.startswith("sceptic-") for call in CALLS) == 2, "drifted evidence the report rests on is re-critiqued"
    assert "- C1: drifted, the page no longer contains the quote" in (topic / "delta" / f"{rc.today()}-3.md").read_text(encoding="utf-8")
    stored = root / json.loads((topic / "claims.json").read_text(encoding="utf-8"))["sources"][0]["stored"]
    assert "results are now in the appendix" in stored.read_text(encoding="utf-8"), "the stored page is what was checked today"
    PHASE["page"] = None

    # Cadence, pause and retire.
    assert living.due(root) == [], "just checked"
    watch["lastChecked"] = "2026-01-01"
    rc.write_json(topic / "watch.json", watch)
    assert living.due(root) == ["retrieval"]
    quiet(research.command_status, root, "retrieval", "pause")
    assert living.due(root) == [] and "resume" in raises(rc.RcError, living.refresh, root, "retrieval")
    quiet(research.command_status, root, "retrieval", "resume")

    # An amended brief is not refreshed; the next run redoes it from plan (claim ids start over, so C5 is gone).
    PHASE["refresh"] = False
    sources_test.ROUTES.pop(0)
    brief = topic / "brief.md"
    brief.write_text(brief.read_text(encoding="utf-8").replace("Which retrieval approach", "Which retrieval method"))
    assert "amended" in raises(rc.RcError, living.refresh, root, "retrieval")
    CALLS.clear()
    quiet(research.run_research, root, "retrieval", None, None)
    assert CALLS[0] == "source-planner", CALLS
    assert json.loads((topic / "watch.json").read_text(encoding="utf-8"))["version"] == version + 2

    quiet(research.command_status, root, "retrieval", "retire")
    assert "retired" in raises(rc.RcError, living.refresh, root, "retrieval")
    assert "retired" in raises(rc.RcError, research.run_research, root, "retrieval", None, None)


def raises(error: type[BaseException], function, *args) -> str:
    try:
        quiet(function, *args)
    except error as caught:
        return str(caught)
    raise AssertionError(f"{function.__name__} did not raise {error.__name__}")


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
    assert research.capped("A", "E") == "E" and research.capped("C", "B") == "C" and research.capped("F", "A") == "F"
    answer = {"question": "Q1", "certainty": "moderate", "downgrades": [{"domain": "inconsistency", "levels": 1, "reason": "trials disagree"}]}
    assert research.answer_problems([answer], ["Q1"], set()) == []
    assert research.certainty_of({"downgrades": [{"levels": 2}, {"levels": 2}], "upgrades": []}) == "very low", "never below very low"
    assert research.certainty_of({"downgrades": [{"levels": 1}], "upgrades": [{"levels": 2}]}) == "high", "never above high"
    problems = " ".join(research.answer_problems([{**answer, "certainty": "high"},
                                                  {"question": "Q2", "certainty": "low", "downgrades": [{"domain": "vibes", "reason": ""}]}],
                                                 ["Q1", "Q2", "Q3"], set()))
    for expected in ("no graded answer for Q3", "add up to 'moderate', not 'high'", "a domain in"):
        assert expected in problems, (expected, problems)
    claims = {"C1", "C2", "C3"}
    good = {"questions": [{"question": "Q1", "assumptions": [{"id": "A1", "text": "x"}],
                           "ach": {"hypotheses": ["H1", "H2"], "matrix": [{"claim": "C1", "ratings": {"H1": "C", "H2": "I"}}]}}]}
    assert research.analysis_problems(good, ["Q1"], claims, PLAN) == []
    unsearched = {**PLAN, "avenues": [avenue for avenue in PLAN["avenues"] if avenue.get("hypothesis") != "H2"]}
    assert "H2 has no disconfirming search" in " ".join(research.analysis_problems(good, ["Q1"], claims, unsearched))
    bad = {"questions": [{"question": "Q1", "assumptions": [],
                          "ach": {"hypotheses": ["H1", "H3"], "matrix": [{"claim": "C9", "ratings": {"H1": "X"}}]}}]}
    problems = " ".join(research.analysis_problems(bad, ["Q1", "Q2"], claims, PLAN))
    for expected in ("no entry for Q2", "name the assumptions", "leaves out hypothesis H2", "H3 is not a hypothesis of the plan",
                     "C9 is not a ledger claim", "rates every hypothesis"):
        assert expected in problems, (expected, problems)
    without = {"questions": [{"question": "Q1", "assumptions": [{"id": "A1", "text": "x"}]}]}
    assert "give an ach matrix" in " ".join(research.analysis_problems(without, ["Q1"], claims, PLAN))
    ranking, diagnostic = research.ach_ranking({"hypotheses": ["H1", "H2"], "matrix": [
        {"claim": "C1", "ratings": {"H1": "I", "H2": "C"}}, {"claim": "C2", "ratings": {"H1": "I", "H2": "I"}},
        {"claim": "C3", "ratings": {"H1": "C", "H2": "I"}}]}, {"C3": "REFUTED"})
    assert ranking == [("H2", 1), ("H1", 2)] and diagnostic == ["C1"], (ranking, diagnostic)
    report = ("## TL;DR\n\n- It is almost certainly hybrid [C1].\n- Assessment: worth a trial.\n\n## Q1: Which?\n\n"
              "Certainty: low.\n\nHybrid is very likely better [C1].\n\nPerhaps dense is fine.\n\n## Caveats\n\nPossibly wrong.")
    problems = " ".join(research.language_problems(report, {"Q1": "low"}))
    assert "'Q1: Which?' says 'perhaps'" in problems and "'very likely', which needs moderate certainty" in problems, problems
    assert "\"Perhaps dense is fine.\" neither cites" in problems and "Caveats" not in problems and "says 'certainly'" not in problems, problems
    assert research.language_problems("## Q1: x\n\nIt is unlikely to matter [C1].", {"Q1": "low"}) == []
    assert research.language_problems("## Q1: x\n\n**Ranking**\n\nIt is unlikely to matter [C1].", {"Q1": "low"}) == [], \
        "a bold label on its own line heads a paragraph; it is not one"
    lead_ins = ("## Q1: x\n\nDense results are mixed:\n\n- one way [C1]\n- uncited bullet\n\n"
                "Assessment: what we would do:\n\n- hash the features\n- score in chunks\n\nAn uncited paragraph.")
    problems = " ".join(research.language_problems(lead_ins, {"Q1": "low"}))
    assert "uncited bullet" in problems and "An uncited paragraph" in problems, problems
    assert "Dense results" not in problems and "hash the features" not in problems and "score in chunks" not in problems, \
        "a lead-in introduces its list, and bullets under an Assessment lead-in are that assessment"
    # The plain summary comes first, stays short, cites nothing and still hedges only with the scale.
    assert "start with a '## In plain words'" in " ".join(research.plain_problems("## TL;DR\n\n- x [C1]."))
    plain = research.plain_problems("## In plain words\n\nIt is probably fine [C1]. " + "word " * 300 + "\n\n## TL;DR\n\n- x [C1].")
    assert len(plain) == 3 and "cites claims" in plain[1] and "'probably'" in plain[2], plain
    assert research.plain_problems("## In plain words\n\n**The short answer**: it is likely fine.\n\n## TL;DR\n\n- x [C1].") == []
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
    # Competing hypotheses: one hypothesis per question is what the first real run's planner wrote; it is rejected
    # unless the question is listed under noAlternatives with a reason.
    lone = {**PLAN, "hypotheses": PLAN["hypotheses"][:1], "avenues": [avenue for avenue in PLAN["avenues"] if avenue.get("hypothesis") != "H2"]}
    assert "Q1 has 1 hypothesis: give it at least two competing answers" in " ".join(research.plan_problems(lone, {"Q1"}, adapters))
    assert research.plan_problems({**lone, "noAlternatives": [{"question": "Q1", "why": "a list of measures"}]}, {"Q1"}, adapters) == []
    assert research.plan_problems({**lone, "noAlternatives": [{"question": "Q1", "why": " "}]}, {"Q1"}, adapters) != [], "a reason is required"
    untagged = {**PLAN, "hypotheses": [{**PLAN["hypotheses"][0], "questions": []}, PLAN["hypotheses"][1]]}
    assert "H1: questions must name the brief questions" in " ".join(research.plan_problems(untagged, {"Q1"}, adapters))
    # An adapter whose key is not in the environment is not offered to the planner.
    with tempfile.TemporaryDirectory() as directory:
        keyed = Path(directory)
        (keyed / "catalog" / "adapters").mkdir(parents=True)
        (keyed / "research-center.json").write_text("{}")
        shutil.copyfile(REPO / "templates" / "packs" / "news" / "adapters" / "guardian.json", keyed / "catalog" / "adapters" / "guardian.json")
        shutil.copyfile(REPO / "templates" / "adapters" / "openalex.json", keyed / "catalog" / "adapters" / "openalex.json")
        saved = research.os.environ.pop("GUARDIAN_API_KEY", None)
        assert list(research.usable_adapters(keyed)) == ["openalex"] and "guardian" not in research.adapter_menu(keyed)
        research.os.environ["GUARDIAN_API_KEY"] = "test-key"
        assert list(research.usable_adapters(keyed)) == ["guardian", "openalex"]
        research.os.environ.pop("GUARDIAN_API_KEY")
        if saved is not None:
            research.os.environ["GUARDIAN_API_KEY"] = saved
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
        assert flow == {"identified": 6, "duplicates": 1, "citationIdentified": 4, "citationDuplicates": 1, "screened": 8,
                        "excluded": 4, "excludedBy": {"X1": 1, "retracted": 3}, "included": 4}, flow
        assert flow["screened"] == flow["excluded"] + flow["included"]
        assert flow["identified"] + flow["citationIdentified"] == flow["screened"] + flow["duplicates"] + flow["citationDuplicates"]
        assert all(row["criterion"] in ("X1", "retracted") for row in screening["records"] if row["decision"] == "exclude")
        assert CALLS.count("screener") == 2, f"one screening per hop: {CALLS}"
        shown = SEEN_PROMPTS["screener"].split("# Candidates, one JSON object per line")[1]
        assert '"id": "R6"' in shown and '"id": "R7"' not in shown, "the retracted citer (R7) skips the screener"

        # Snowball: from the included key work (W100) one reference (W400) and its citers were followed, screened and stored;
        # a citer Crossref lists as retracted was excluded before screening, though OpenAlex did not flag it.
        rows = {row["key"]: row for row in screening["records"]}
        reference, citer, retracted = rows["doi:10.5555/meta.1999"], rows["doi:10.5555/new.trial"], rows["doi:10.5555/retracted.trial"]
        assert reference["hop"] == 1 and reference["via"] == ["R1 backward", "R1 forward"] and reference["decision"] == "include"
        assert citer["via"] == ["R1 forward"] and citer["decision"] == "include" and (root / citer["stored"]).is_file()
        assert "Hours fell and output held steady." in (root / citer["stored"]).read_text()
        assert retracted["decision"] == "exclude" and retracted["criterion"] == "retracted"
        assert screening["retractionCheck"] == ["no DOIs to check", "3 DOIs checked, 1 retracted"], screening["retractionCheck"]
        citations = json.loads((topic / "citations.json").read_text())
        assert [entry.get("direction") or "retractions" for entry in citations] == ["backward", "forward", "retractions"], citations
        assert "hop 1: R1 forward" in (topic / "screening.md").read_text()
        included = [row for row in screening["records"] if row["decision"] == "include"]
        record_text = (root / included[0]["stored"]).read_text()
        assert included[0]["stored"].startswith("sources/search-retrieval/") and "Output per hour rose by 7 percent." in record_text
        assert "## Excluded" in (topic / "screening.md").read_text()

        ledger = json.loads((topic / "claims.json").read_text())
        assert [source["url"] for source in ledger["sources"]] == [PAPER, DEAD, RECORD], "PAPER and BLOG merge into one source"
        assert ledger["sources"][0]["foundBy"] == ["researcher-claude", "researcher-sonnet"]
        assert ledger["sources"][1]["stored"] is None and ledger["sources"][1]["fetch"].startswith("failed")
        assert ledger["sources"][2]["record"] == included[0]["id"] and ledger["sources"][2]["stored"] == included[0]["stored"]
        assert [claim["quoteVerified"] for claim in ledger["claims"]] == [True, False, False, True], \
            "the record's claim is checked against its stored abstract, not a download"

        # Grading: reliability is capped by the evidence type, a record keeps its adapter's type, via is traced or not.
        paper, dead, record = ledger["sources"]
        assert (paper["evidenceType"], paper["reliability"]) == ("peer-reviewed", "B") and paper["checkedAt"] == rc.today()
        assert (dead["evidenceType"], dead["reliability"]) == ("forum", "E") and "said A; forum is at best E" in dead["reliabilityCapped"]
        assert record["evidenceType"] == "peer-reviewed", "an included record keeps the evidence type its adapter gave it"
        assert (ledger["claims"][1]["traced"], ledger["claims"][2]["traced"]) == (True, False), "via resolved against the ledger"
        assert "| B | no | the authors' own benchmark table, https://www.example.org/paper/ (traced) |" in (topic / "claims.md").read_text()
        judgement = json.loads((topic / "judgement.json").read_text())
        assert [item["credibility"] for item in judgement["claims"]] == [2, 3, 6] and judgement["answers"][0]["certainty"] == "low"
        assert "- Q1: **low**" in (topic / "judgement.md").read_text()
        stored = root / ledger["sources"][0]["stored"]
        assert stored.is_file() and PAGE in stored.read_text()
        assert json.loads((root / "catalog" / "sources" / "web-retrieval.json").read_text())["origin"] == "research:retrieval"

        assert CALLS.count("analyst") == 2 and CALLS.count("reporter") == 2, f"one retry each: {CALLS}"
        assert CALLS.count("researcher-sonnet") == 2, f"a malformed reply is retried: {CALLS}"
        assert EXTRA not in json.dumps(ledger), "a source past the limit is dropped with its claim"
        assert "C99" in SEEN_PROMPTS["analyst"], "the retry names the problem"

        reviews = sorted(path.name for path in (topic / "critique").glob("*.json"))
        assert reviews == ["review-a.json", "review-b.json"], reviews
        mapping = json.loads((root / ".rc-local" / "research" / "retrieval" / "reviewers.json").read_text())
        assert sorted(mapping.values()) == ["sceptic-claude", "sceptic-sonnet"]
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
        assert "## Evidence" in report and "| C1 | HOLDS | 2 | B | yes | [Paper \\| Site](" in report and "## Contested" in report
        assert "## Certainty of the answers" in report and "- Q1: **low** (imprecision -1: one benchmark; one-sided -1:" in report
        assert "C3 (UNSUPPORTED)" in report and "## Handoff" in report
        assert "says 'probably'" in SEEN_PROMPTS["reporter"], "a vague hedge in an answer is rejected"
        assert "## Competing hypotheses for Q1" in report and "1. H1: Hybrid retrieval gives the best recall (0 inconsistent)" in report
        assert "2. H2: Dense retrieval alone gives the best recall (1 inconsistent)" in report, "C3 is unsupported, so only C1 counts against H2"
        assert "Diagnostic claims, the ones that tell the hypotheses apart: C1, C2." in report and "Learned sparse retrieval alone" in report
        assert "| A1: Recall on public benchmarks predicts recall on our catalogue | Q1 | WEAK |" in report
        assert "| C1 | C | I |" in (topic / "analysis.md").read_text() and "A1" in SEEN_PROMPTS["sceptic-claude"].split("# Task")[1]
        assert "## How the sources were found" in report and "- Duplicates removed: 1" in report and "X1 (Published before 2025): 1" in report

        validator = __import__("importlib.util").util
        spec = validator.spec_from_file_location("validate_rc", REPO / "scripts" / "validate-research-center.py")
        module = validator.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.validate(root) == [], module.validate(root)
        original = (topic / "judgement.json").read_text()
        tampered = json.loads(original)
        tampered["answers"][0].pop("certainty")
        tampered["answers"][0]["downgrades"][0]["reason"] = " "
        (topic / "judgement.json").write_text(json.dumps(tampered))
        errors = " ".join(module.validate(root))
        assert "the answer to Q1 has no certainty" in errors and "imprecision grade of Q1 gives no reason" in errors, errors
        (topic / "judgement.json").write_text(original)

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
            quiet(research.run_research, root, "retrieval", "critique", 1)
            raise AssertionError("the budget must stop the run")
        except rc.BudgetExceeded:
            pass
        assert (topic / "analysis.md").is_file() and not (topic / "report.md").exists()
        # The sceptics that answered before the budget ran out are not paid for again.
        replies = root / ".rc-local" / "research" / "retrieval" / "replies"
        assert len(list((replies / "critique").glob("*.json"))) == 1, list(replies.rglob("*"))
        CALLS.clear()
        quiet(research.run_research, root, "retrieval", None, None)
        assert sum(call.startswith("sceptic-") for call in CALLS) == 1 and CALLS[-1] == "reporter", CALLS
        assert not any(replies.rglob("*.json")), "finished stages keep no replies"

        test_living(root, topic)
    print("research test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
