#!/usr/bin/env python3
"""./rc research: a topic's brief, then a fixed, resumable pipeline that ends in a cited report.

plan     source-planner turns the brief into adapter queries,   -> source-plan.json
         hypotheses with disconfirming searches, a horizon
         and numbered exclusion criteria
search   the runner runs every adapter query (no agent)         -> searches.json, candidates.json
screen   the screener includes or excludes each candidate     -> screening.json (+ sources/search-<topic>/)
         against the criteria, with a reason; the runner
         stores the included records' text
collect  researchers read the included records, search the    -> claims.json (+ sources/web-<topic>/)
         web in parallel; the runner stores every cited
         page and checks every quote
analyze  analyst answers the questions from the ledger        -> analysis.md, ideas.json
critique sceptics try to disprove each claim, in parallel     -> critique/review-<x>.json
judge    the judge reads the reviews as anonymous labels      -> judgement.json
apply    applier fits surviving ideas to the user's repos     -> fit.json, fit.md, handoff.md
report   reporter writes the answer; the runner checks it     -> report.md (with the screening flow)

Each stage's output is committed under research/<topic>/; a run resumes at the first missing output. A topic whose
brief has a cadence stays living afterwards: ./rc research refresh (living.py) keeps it current.
See docs/decisions/0004-research-pipeline.md, 0008-search-and-screen.md and 0009-living-topics.md.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import http.client
import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "runner"))
sys.path.insert(0, str(HERE.parent / "ingest"))
sys.path.insert(0, str(HERE.parent / "sources"))
import extract  # noqa: E402
import ingest  # noqa: E402
import kit  # noqa: E402
import rc  # noqa: E402
import sources as registry  # noqa: E402

STAGES = ("plan", "search", "screen", "collect", "analyze", "critique", "judge", "apply", "report")
OUTPUTS = {
    "plan": ["source-plan.json", "source-plan.md"],
    "search": ["searches.json", "candidates.json"],
    "screen": ["screening.json", "screening.md", "citations.json"],
    "collect": ["claims.json", "claims.md"],
    "analyze": ["analysis.md", "ideas.json"],
    "critique": ["critique"],
    "judge": ["judgement.json", "judgement.md"],
    "apply": ["fit.json", "fit.md", "handoff.md"],
    "report": ["report.md"],
}
CLAIM_VERDICTS = ("HOLDS", "WEAK", "REFUTED", "UNSUPPORTED")
IDEA_VERDICTS = ("SURVIVES", "WEAKENED", "FALLS")
RINGS = ("ADOPT", "TRIAL", "ASSESS", "HOLD")
EFFORTS = ("S", "M", "L")
SECTIONS = ("Topic", "Questions", "Scope", "Out of scope", "Our needs", "Success criteria", "Source preferences", "Living")
# How often a living topic is refreshed, in days; derived follows the plan's horizon (living.py). none is one-shot.
CADENCES = {"none": 0, "weekly": 7, "monthly": 30, "quarterly": 91, "derived": -1}
# draft -> accepted -> living (after the first full run of a topic with a cadence) <-> paused; retired is final.
TOPIC_STATUSES = ("draft", "accepted", "living", "paused", "retired")
QUESTION = re.compile(r"^- (Q\d+):\s*(\S.*)$", re.MULTILINE)
# One bracket may cite several claims: [C3], [C3, C7] and [C3; C7] all count.
CLAIM_REF = re.compile(r"\[(C\d+(?:\s*[,;]\s*C\d+)*)\]")
IDEA_ID = re.compile(r"I\d+")
# Admiralty grading (docs/decisions/0010-evidence-grading.md): how reliable a source is, A best, F cannot be judged,
# graded separately from how credible a claim is, 1 confirmed .. 6 cannot be judged.
GRADES = ("A", "B", "C", "D", "E", "F")
CREDIBILITY = (1, 2, 3, 4, 5, 6)
# GRADE-style certainty per answer: it starts high and every downgrade lowers it by its levels.
CERTAINTIES = ("very low", "low", "moderate", "high")
DOWNGRADES = ("reliability", "inconsistency", "indirectness", "imprecision", "one-sided")
UPGRADES = ("large-effect", "convergence")
# Analysis of Competing Hypotheses: each relied-on claim is consistent (C), inconsistent (I) or neutral (N) with each.
RATINGS = ("C", "I", "N")
ASSUMPTION_ID = re.compile(r"A\d+")
# ICD 203 likelihood words and the least certainty each may be said with; longest phrases are matched first.
LIKELIHOOD = {
    "almost no chance": "high", "almost certainly": "high", "almost certain": "high", "very unlikely": "moderate",
    "very likely": "moderate", "roughly even chance": "low", "unlikely": "low", "likely": "low",
}
SCALE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, LIKELIHOOD), key=len, reverse=True)) + r")\b")
# Hedges that read as likelihood but map to no number; the scale says it instead.
VAGUE = re.compile(r"\b(probably|possibly|perhaps|presumably|conceivably|undoubtedly|definitely|certainly|"
                   r"probable|improbable|doubtful|in all likelihood)\b")
WEB = "web"  # the avenue the researcher roles search themselves; every other avenue names an adapter
STANCES = ("support", "disconfirm", "explore")
HORIZONS = ("near", "medium", "long")
HYPOTHESIS_ID = re.compile(r"H\d+")
CRITERION_ID = re.compile(r"X\d+")
# Every screening may exclude for this; the planner adds X1.. from the brief.
OFF_TOPIC = {"id": "X0", "text": "Bears on none of the brief's questions", "from": "Questions"}
RETRACTED = "retracted"  # an exclusion the runner makes itself, from the adapters' retraction flags
MIN_QUOTE_WORDS = 6
# Words a quote must never lose or gain in a fuzzy match: they flip or change what it says.
NEGATIONS = frozenset({"not", "no", "never", "none", "nor", "without", "cannot", "t"})


def evidence_types(root: Path) -> dict[str, dict[str, Any]]:
    """The instance's evidence types (catalog/evidence-types.json), or the template's defaults."""
    path = root / "catalog" / "evidence-types.json"
    if not path.is_file():
        path = HERE.parent.parent / "templates" / "evidence-types.json"
    return {item["id"]: item for item in rc.load_json(path)["types"]}


def capped(grade: str, ceiling: str) -> str:
    """A source is never graded more reliable than its evidence type allows: a forum post is at best E."""
    return grade if grade == "F" else max(grade, ceiling, key=GRADES.index)


def certainty_of(answer: dict[str, Any]) -> str:
    """The certainty an answer's downgrades and upgrades add up to, starting from high."""
    level = len(CERTAINTIES) - 1 - sum(int(item.get("levels", 1)) for item in answer.get("downgrades", []))
    level += sum(int(item.get("levels", 1)) for item in answer.get("upgrades", []))
    return CERTAINTIES[min(max(level, 0), len(CERTAINTIES) - 1)]


def answer_problems(answers: Any, known: list[str], claim_ids: set[str]) -> list[str]:
    """Why a set of graded answers does not hold: every question needs one, with a certainty its named, reasoned
    downgrades and upgrades add up to."""
    if not isinstance(answers, list):
        return ['expected "answers": [{"question", "certainty", "downgrades": [...], "upgrades": [...]}]']
    seen = {item.get("question"): item for item in answers if isinstance(item, dict)}
    problems = [f"no graded answer for {question}" for question in known if question not in seen]
    for question, item in seen.items():
        if item.get("certainty") not in CERTAINTIES:
            problems.append(f"{question}: certainty must be one of {CERTAINTIES}")
            continue
        for kind, allowed in (("downgrades", DOWNGRADES), ("upgrades", UPGRADES)):
            for entry in item.get(kind, []):
                if entry.get("domain") not in allowed or entry.get("levels", 1) not in (1, 2) or not str(entry.get("reason", "")).strip():
                    problems.append(f"{question}: each of {kind} needs a domain in {allowed}, levels 1 or 2, and a reason")
                problems += [f"{question}: {kind} cites unknown claim {claim}" for claim in set(entry.get("claims", [])) - claim_ids]
        if certainty_of(item) != item["certainty"]:
            problems.append(f"{question}: the downgrades and upgrades add up to {certainty_of(item)!r}, not {item['certainty']!r}")
    return problems


def plan_hypotheses(plan: dict[str, Any], question: str) -> list[str]:
    """The plan's hypotheses about one question; two or more make it a question of competing hypotheses."""
    return [item["id"] for item in plan.get("hypotheses", []) if question in item.get("questions", [])]


def analysis_problems(data: dict[str, Any], known: list[str], claim_ids: set[str], plan: dict[str, Any]) -> list[str]:
    """The structured part of an analysis (ACH, Heuer; key assumptions check): every question lists the assumptions
    its answer rests on; a question the plan gave two or more hypotheses gets a matrix rating every relied-on claim
    as consistent (C), inconsistent (I) or neutral (N) with each of them, and only hypotheses that were searched
    against may be weighed."""
    entries = data.get("questions")
    if not isinstance(entries, list):
        return ['expected "questions": [{"question", "assumptions": [...], "ach": {...}}] next to "ideas"']
    seen = {entry.get("question"): entry for entry in entries if isinstance(entry, dict)}
    problems = [f"no entry for {question} in questions" for question in known if question not in seen]
    disconfirmed = {avenue.get("hypothesis") for avenue in plan.get("avenues", []) if avenue.get("stance") == "disconfirm"}
    assumption_ids: list[str] = []
    for question, entry in seen.items():
        assumptions = entry.get("assumptions")
        if not isinstance(assumptions, list) or not assumptions:
            problems.append(f"{question}: name the assumptions its answer rests on (at least one)")
            assumptions = []
        for item in assumptions:
            if not ASSUMPTION_ID.fullmatch(str(item.get("id", ""))) or not str(item.get("text", "")).strip():
                problems.append(f"{question}: assumption {item} needs an id like A1 and a text")
            assumption_ids.append(item.get("id"))
            problems += [f"{question}: assumption {item.get('id')} cites unknown claim {claim}" for claim in set(item.get("claims", [])) - claim_ids]
        expected = plan_hypotheses(plan, question)
        ach = entry.get("ach")
        if len(expected) < 2 and not ach:
            continue
        if not isinstance(ach, dict):
            problems.append(f"{question}: the plan weighs {', '.join(expected)} against each other; give an ach matrix")
            continue
        hypotheses = ach.get("hypotheses") or []
        problems += [f"{question}: the matrix leaves out hypothesis {hypothesis}" for hypothesis in expected if hypothesis not in hypotheses]
        for hypothesis in hypotheses:
            if hypothesis not in {item["id"] for item in plan.get("hypotheses", [])}:
                problems.append(f"{question}: {hypothesis} is not a hypothesis of the plan; list an alternative nobody searched for under untested")
            elif hypothesis not in disconfirmed:
                problems.append(f"{question}: {hypothesis} has no disconfirming search in the plan, so it cannot be weighed")
        if len(hypotheses) < 2:
            problems.append(f"{question}: a matrix weighs at least two hypotheses; leave ach out for a question the plan gave fewer")
        rows = ach.get("matrix")
        if not isinstance(rows, list) or not rows:
            problems.append(f"{question}: the matrix needs a row per claim the answer relies on")
            rows = []
        for row in rows:
            if row.get("claim") not in claim_ids:
                problems.append(f"{question}: matrix row {row.get('claim')} is not a ledger claim")
            ratings = row.get("ratings") or {}
            if any(ratings.get(hypothesis) not in RATINGS for hypothesis in hypotheses):
                problems.append(f"{question}: row {row.get('claim')} rates every hypothesis as one of {RATINGS}")
    duplicates = sorted({identifier for identifier in assumption_ids if assumption_ids.count(identifier) > 1})
    problems += [f"assumption id {identifier} is used twice" for identifier in duplicates if identifier]
    return problems


def ach_ranking(ach: dict[str, Any], verdicts: dict[str, str]) -> tuple[list[tuple[str, int]], list[str]]:
    """Heuer's reading of a matrix: hypotheses ranked by how much surviving evidence is inconsistent with them
    (fewest first), and the diagnostic claims, those rated differently across the hypotheses. Claims judged
    REFUTED or UNSUPPORTED do not count."""
    rows = [row for row in ach["matrix"] if verdicts.get(row["claim"]) not in ("REFUTED", "UNSUPPORTED")]
    score = {hypothesis: sum(row["ratings"][hypothesis] == "I" for row in rows) for hypothesis in ach["hypotheses"]}
    diagnostic = [row["claim"] for row in rows if len({row["ratings"][hypothesis] for hypothesis in ach["hypotheses"]}) > 1]
    return sorted(score.items(), key=lambda item: (item[1], int(item[0][1:]))), diagnostic


def language_problems(markdown: str, certainty: dict[str, str]) -> list[str]:
    """ICD 203 for the report: likelihood is said only with the fixed scale, never stronger than the question's
    certainty allows, and every paragraph of the TL;DR and the answers cites evidence [C#] or says it is an
    Assessment."""
    problems = []
    parts = re.split(r"^## (.+)$", markdown, flags=re.MULTILINE)
    for heading, body in zip(parts[1::2], parts[2::2]):
        question = re.match(r"(Q\d+)\b", heading.strip())
        if heading.strip() != "TL;DR" and not question:
            continue
        lowered = body.lower()
        # "almost certainly" is on the scale; its "certainly" is not a hedge of its own.
        for word in sorted({match.group(0) for match in VAGUE.finditer(SCALE.sub(" ", lowered))}):
            problems.append(f"'{heading.strip()}' says '{word}': use the likelihood scale ({', '.join(LIKELIHOOD)}) or plain fact")
        if question and question.group(1) in certainty:
            have = CERTAINTIES.index(certainty[question.group(1)])
            for word in sorted({match.group(0) for match in SCALE.finditer(lowered)}):
                if CERTAINTIES.index(LIKELIHOOD[word]) > have:
                    problems.append(f"'{heading.strip()}' says '{word}', which needs {LIKELIHOOD[word]} certainty; "
                                    f"the judgement gives {certainty[question.group(1)]}")
        for unit in re.split(r"\n\s*\n|\n(?=\s*[-*] )", body.strip()):
            text = unit.strip()
            if text and not claim_refs(text) and not re.match(r"^(?:[-*]\s*)?(?:\*\*)?(Assessment|Certainty)\b", text):
                problems.append(f"'{heading.strip()}': \"{text[:70]}\" neither cites a claim [C#] nor starts with 'Assessment:'")
    return problems


def claim_refs(text: str) -> list[str]:
    """Every claim id cited in text, in order of appearance."""
    return [claim for group in CLAIM_REF.findall(text) for claim in re.split(r"\s*[,;]\s*", group)]


# Topics and briefs ----------------------------------------------------------------------------------------


def topic_dir(root: Path, topic: str) -> Path:
    if not ingest.ID.fullmatch(topic):
        raise rc.RcError(f"topic id must be lowercase hyphen-case: {topic}")
    return root / "research" / topic


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[index].strip(): parts[index + 1].strip() for index in range(1, len(parts) - 1, 2)}


def brief_problems(text: str) -> list[str]:
    problems = []
    found = sections(text)
    for name in SECTIONS:
        body = found.get(name, "")
        if not body:
            problems.append(f"section '## {name}' is missing or empty")
        elif re.search(r"<[^>\n]+>", body):
            problems.append(f"section '## {name}' still holds a <placeholder>")
    if not QUESTION.findall(text):
        problems.append("'## Questions' needs at least one line '- Q1: ...'")
    if found.get("Living") and not re.search(r"<[^>\n]+>", found["Living"]):
        living = brief_living(text)
        if living["cadence"] not in CADENCES:
            problems.append(f"'## Living' needs a line 'Cadence: ...', one of {', '.join(CADENCES)}")
        elif living["cadence"] != "none" and not living["retireWhen"]:
            problems.append("'## Living' needs a line 'Retire when: ...': when this topic stops being worth refreshing")
    return problems


def brief_living(text: str) -> dict[str, str]:
    """The brief's Living section: how often to refresh and when to stop."""
    body = sections(text).get("Living", "")
    cadence = re.search(r"^Cadence:\s*(\S+)", body, flags=re.MULTILINE)
    retire = re.search(r"^Retire when:\s*(\S.*)$", body, flags=re.MULTILINE)
    return {"cadence": cadence.group(1).lower() if cadence else "none", "retireWhen": retire.group(1).strip() if retire else ""}


def brief_hash(text: str) -> str:
    """What the research was built on: the brief without its Status line and its Amendments log, so changing the
    status or logging an amendment does not count, but changing any question, scope or need does."""
    body = re.sub(r"^Status:.*$", "", text, count=1, flags=re.MULTILINE)
    body = re.sub(r"^## Amendments\n.*?(?=^## |\Z)", "", body, flags=re.MULTILINE | re.DOTALL)
    return hashlib.sha256(" ".join(body.split()).encode("utf-8")).hexdigest()


def brief_status(text: str) -> str:
    match = re.search(r"^Status:\s*(\S+)", text, flags=re.MULTILINE)
    return match.group(1) if match else "unknown"


def set_status(root: Path, topic: str, status: str) -> None:
    if status not in TOPIC_STATUSES:
        raise rc.RcError(f"status must be one of {TOPIC_STATUSES}")
    path = topic_dir(root, topic) / "brief.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"^Status:\s*\S+", f"Status: {status}", text, count=1, flags=re.MULTILINE), encoding="utf-8", newline="\n")


def command_new(root: Path, args: argparse.Namespace) -> None:
    rc.settings(root)
    directory = topic_dir(root, args.topic)
    if directory.exists():
        raise rc.RcError(f"topic already exists: {args.topic}")
    template = (root / "templates" / "brief.md").read_text(encoding="utf-8")
    title = " ".join(args.title.split())
    rc.write_text(directory / "brief.md", template.replace("<topic-id>", args.topic).replace("<title>", title))
    print(f"created research/{args.topic}/brief.md; fill it with the grill-research-topic skill, then ./rc research accept {args.topic}")


def command_accept(root: Path, args: argparse.Namespace) -> None:
    path = topic_dir(root, args.topic) / "brief.md"
    text = path.read_text(encoding="utf-8")
    problems = brief_problems(text)
    if problems:
        raise rc.RcError("brief is not ready:\n" + "\n".join(f"- {problem}" for problem in problems))
    set_status(root, args.topic, "accepted")
    print(f"accepted research/{args.topic}/brief.md; run it with ./rc research run {args.topic}")


def stage_done(directory: Path, stage: str) -> bool:
    if stage == "critique":
        return any((directory / "critique").glob("review-*.json"))
    if stage == "apply":
        return (directory / "fit.json").is_file()
    return all((directory / name).exists() for name in OUTPUTS[stage])


def command_status(root: Path, topic: str, action: str) -> None:
    """pause and resume a living topic's refreshes, or retire it for good."""
    if not (topic_dir(root, topic) / "brief.md").is_file():
        raise rc.RcError(f"no topic {topic}; ./rc research list shows them")
    status = brief_status((topic_dir(root, topic) / "brief.md").read_text(encoding="utf-8"))
    allowed = {"pause": ("living",), "resume": ("paused",), "retire": ("accepted", "living", "paused")}
    if status not in allowed[action]:
        raise rc.RcError(f"research/{topic} is {status}; {action} needs one of {allowed[action]}")
    set_status(root, topic, {"pause": "paused", "resume": "living", "retire": "retired"}[action])
    print(f"research/{topic} is now {'paused' if action == 'pause' else 'living' if action == 'resume' else 'retired'}")


def command_list(root: Path, _: argparse.Namespace) -> None:
    for brief in sorted((root / "research").glob("*/brief.md")):
        directory = brief.parent
        done = [stage for stage in STAGES if stage_done(directory, stage)]
        title = brief.read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
        watch = rc.load_json(directory / "watch.json") if (directory / "watch.json").is_file() else None
        living = (f"  v{watch['version']}, checked {watch['lastChecked']}, every {watch['cadenceDays']} days" if watch else "")
        print(f"{directory.name:<32} {brief_status(brief.read_text(encoding='utf-8')):<9} {len(done)}/{len(STAGES)} stages  {title}{living}")


def command_show(root: Path, args: argparse.Namespace) -> None:
    directory = topic_dir(root, args.topic)
    text = (directory / "brief.md").read_text(encoding="utf-8")
    print(f"{args.topic}: brief {brief_status(text)}")
    for stage in STAGES:
        print(f"  {'✓' if stage_done(directory, stage) else '·'} {stage:<9} {', '.join(OUTPUTS[stage])}")
    if (directory / "report.md").is_file():
        print(f"report: research/{args.topic}/report.md")


# Shared context -------------------------------------------------------------------------------------------


def context(root: Path, topic: str) -> str:
    """What every research role reads first: the brief, the profile, and the ingested sources."""
    lines = [f"Topic: {topic}. Brief: research/{topic}/brief.md (read it first)."]
    if (root / "knowledge" / "profile" / "index.md").is_file():
        lines.append("Profile of the user or company: knowledge/profile/index.md and the notes it links.")
    else:
        lines.append("No profile: nothing was ingested, so judge needs from the brief alone.")
    owned = [descriptor for descriptor in ingest.sources(root) if descriptor.get("origin", "user") == "user"]
    if owned:
        lines.append("Ingested sources (text under sources/<id>/text/, digest at knowledge/digests/<id>.md):")
        lines += [f"- {item['id']} ({item['kind']}): {' '.join(item['locators'])} {item.get('note', '')}".rstrip() for item in owned]
    return "\n".join(lines)


def questions(root: Path, topic: str) -> list[str]:
    return [identifier for identifier, _ in QUESTION.findall((topic_dir(root, topic) / "brief.md").read_text(encoding="utf-8"))]


def json_reply(check):
    """Wrap a check of parsed JSON so a parse failure becomes a retry."""
    return lambda reply: check(rc.extract_json(reply))


# Stages ---------------------------------------------------------------------------------------------------


def usable_adapters(root: Path) -> dict[str, dict[str, Any]]:
    """The enabled adapters that can run here: one whose key is not in the environment would only fail, so the
    planner is not offered it."""
    return {identifier: spec for identifier, spec in registry.descriptors(root).items()
            if not spec.get("needsKeyEnv") or os.environ.get(spec["needsKeyEnv"])}


def adapter_menu(root: Path) -> str:
    """What the planner may choose from: every usable adapter's coverage, query syntax and filters, plus the web."""
    lines = [f"- `{WEB}`: the researcher roles search the open web themselves (Claude and GPT). Use it for what no adapter covers."]
    for identifier, spec in usable_adapters(root).items():
        filters = "; ".join(f"{name}: {text}" for name, text in spec.get("filters", {}).items()) or "none"
        lines.append(f"- `{identifier}` ({spec['family']}): {spec['covers']} Query: {spec['queryHelp']} Filters: {filters}.")
    return "\n".join(lines)


def plan_problems(data: Any, known: set[str], adapters: dict[str, dict[str, Any]]) -> list[str]:
    """Why a source plan cannot be searched as it stands; empty when it can."""
    if not isinstance(data, dict) or not isinstance(data.get("avenues"), list) or not data["avenues"]:
        return ['expected {"avenues": [...], "hypotheses": [...], "horizon": "...", "exclusions": [...]}']
    problems = []
    if data.get("horizon") not in HORIZONS:
        problems.append(f"horizon must be one of {HORIZONS}")
    hypotheses = data.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        problems.append("name at least one hypothesis (H1, H2, ...): the answers you expect, so they can be searched against")
        hypotheses = []
    hypothesis_ids = set()
    for hypothesis in hypotheses:
        if not HYPOTHESIS_ID.fullmatch(str(hypothesis.get("id", ""))) or not hypothesis.get("statement"):
            problems.append(f"hypothesis {hypothesis} needs an id like H1 and a statement")
        unknown = set(hypothesis.get("questions") or []) - known
        if unknown or not hypothesis.get("questions"):
            problems.append(f"hypothesis {hypothesis.get('id')}: questions must name the brief questions it answers")
        hypothesis_ids.add(hypothesis.get("id"))
    # A question gets competing answers, so the analysis can weigh them (ACH), unless the planner says why it has none.
    single = data.get("noAlternatives") if isinstance(data.get("noAlternatives"), list) else []
    excused = {item.get("question") for item in single if isinstance(item, dict) and str(item.get("why", "")).strip()}
    for question in sorted(known, key=lambda value: int(value[1:])):
        answers = [item.get("id") for item in hypotheses if question in (item.get("questions") or [])]
        if len(answers) < 2 and question not in excused:
            problems.append(f"{question} has {len(answers)} hypothesis: give it at least two competing answers, or list it under "
                            "noAlternatives with why it has none")
    exclusions = data.get("exclusions") if isinstance(data.get("exclusions"), list) else []
    for criterion in exclusions:
        if not CRITERION_ID.fullmatch(str(criterion.get("id", ""))) or criterion.get("id") == OFF_TOPIC["id"] or not criterion.get("text"):
            problems.append(f"exclusion {criterion} needs an id X1, X2, ... (X0 is reserved) and a text")
        if criterion.get("from") not in SECTIONS:
            problems.append(f"exclusion {criterion.get('id')} must name the brief section it comes from, one of {SECTIONS}")
    covered, disconfirmed, families = set(), set(), set()
    for number, avenue in enumerate(data["avenues"], 1):
        label = f"avenue {number} ({avenue.get('adapter')})"
        adapter = avenue.get("adapter")
        if adapter != WEB and adapter not in adapters:
            problems.append(f"{label}: adapter must be {WEB} or one of {sorted(adapters)}")
            continue
        if not str(avenue.get("query", "")).strip() or not avenue.get("why"):
            problems.append(f"{label}: needs a query and a why")
        if avenue.get("stance") not in STANCES:
            problems.append(f"{label}: stance must be one of {STANCES}")
        unknown = set(avenue.get("questions") or []) - known
        if unknown or not avenue.get("questions"):
            problems.append(f"{label}: questions must name brief questions, not {sorted(unknown) or 'none'}")
        covered |= set(avenue.get("questions") or [])
        if avenue.get("stance") == "disconfirm":
            if avenue.get("hypothesis") not in hypothesis_ids:
                problems.append(f"{label}: a disconfirming avenue names the hypothesis it tests")
            disconfirmed.add(avenue.get("hypothesis"))
        if adapter == WEB:
            continue
        families.add(adapters[adapter]["family"])
        bad = set(avenue.get("filters") or {}) - set(adapters[adapter].get("filters", {}))
        if bad:
            problems.append(f"{label}: {adapter} has no filter {sorted(bad)}")
        if avenue.get("since"):
            try:
                datetime.date.fromisoformat(avenue["since"])
            except (TypeError, ValueError):
                problems.append(f"{label}: since must be YYYY-MM-DD")
    problems += [f"no avenue serves {question}" for question in sorted(known - covered)]
    problems += [f"{hypothesis} has no disconfirming avenue: search for evidence that it is wrong"
                 for hypothesis in sorted(hypothesis_ids - disconfirmed) if hypothesis]
    available = {spec["family"] for spec in adapters.values()}
    if len(families) < min(2, len(available)):
        problems.append(f"use adapters from at least two families besides the web; available: {sorted(available)}")
    return problems


def stage_plan(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    known, adapters = set(questions(root, topic)), usable_adapters(root)

    def check(data: Any) -> dict[str, Any]:
        problems = plan_problems(data, known, adapters)
        if problems:
            raise ValueError("; ".join(problems[:20]))
        return data

    body = f"# Task\n\nPlan where to search.\n\n{context(root, topic)}\n\n# Avenues you can plan\n\n{adapter_menu(root)}"
    data = session.call_checked(config["pipeline"]["sourcePlanner"], body, "plan", json_reply(check))
    data["exclusions"] = [OFF_TOPIC, *data.get("exclusions", [])]
    directory = topic_dir(root, topic)
    # Everything after this plan was built on this brief; a later amendment makes it all stale (run_research).
    data["briefHash"] = brief_hash((directory / "brief.md").read_text(encoding="utf-8"))
    rc.write_json(directory / "source-plan.json", data)
    lines = [f"# Source plan: {topic}\n", f"Horizon: {data['horizon']}\n", "## Hypotheses\n"]
    lines += [f"- {item['id']}: {item['statement']}" for item in data["hypotheses"]]
    lines += [f"- {item['question']} has no competing answers: {item['why']}" for item in data.get("noAlternatives", [])]
    lines += ["", "## Exclusion criteria\n"] + [f"- {item['id']}: {item['text']} (from {item['from']})" for item in data["exclusions"]]
    lines += ["", "## Avenues\n", "| # | Adapter | Query | Filters | Since | Stance | Questions | Why |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for number, avenue in enumerate(data["avenues"], 1):
        stance = avenue["stance"] + (f" {avenue['hypothesis']}" if avenue.get("hypothesis") else "")
        filters = ", ".join(f"{key}={value}" for key, value in (avenue.get("filters") or {}).items())
        lines.append(f"| {number} | {avenue['adapter']} | {cell(avenue['query'])} | {cell(filters)} | {avenue.get('since') or ''} | "
                     f"{stance} | {', '.join(avenue['questions'])} | {cell(avenue['why'])} |")
    rc.write_text(directory / "source-plan.md", "\n".join(lines))


def stage_search(session: rc.Session, root: Path, topic: str) -> None:
    """Run every adapter avenue of the plan. No agent is called; each query is logged in searches.json."""
    config = rc.settings(root)
    directory = topic_dir(root, topic)
    plan = rc.load_json(directory / "source-plan.json")
    log = directory / "searches.json"
    log.unlink(missing_ok=True)
    limit = config["research"].get("resultsPerQuery", 20)
    found, failed, tried = [], 0, 0
    for number, avenue in enumerate(plan["avenues"], 1):
        if avenue["adapter"] == WEB:
            continue
        tried += 1
        try:
            records = registry.search(root, avenue["adapter"], avenue["query"], avenue.get("filters") or {}, avenue.get("since"), limit, log)
        except kit.AdapterError as error:
            failed += 1
            session.say(f"search {number} ({avenue['adapter']}): failed, {error}", "warn")
            continue
        session.say(f"search {number} ({avenue['adapter']}): {len(records)} results for {avenue['query']!r}")
        found += [{**item, "avenue": number, "questions": avenue["questions"]} for item in records]
    if tried and failed == tried:
        raise rc.RcError("every adapter search failed (see searches.json); the run stops rather than becoming web-only")
    merged = registry.merge(found)
    for number, item in enumerate(merged, 1):
        same = [other for other in found if other["key"] == item["key"]]
        item["id"] = f"R{number}"
        item["avenues"] = sorted({other["avenue"] for other in same})
        item["questions"] = sorted({question for other in same for question in other["questions"]})
        item.pop("avenue", None)
    rc.write_json(directory / "candidates.json", {"identified": len(found), "records": merged})
    session.say(f"search: {len(found)} results, {len(found) - len(merged)} duplicates, {len(merged)} candidates to screen")


def candidate_line(item: dict[str, Any]) -> str:
    venue = item["extra"].get("venue") or item["extra"].get("domain") or ""
    return json.dumps({"id": item["id"], "title": item["title"], "type": item["evidenceType"], "date": item["date"] or "undated",
                       "by": ", ".join(item["authors"][:3]), "venue": venue, "url": item["url"], "questions": item["questions"],
                       "found": item.get("via") or item["foundBy"],
                       "abstract": item["abstract"][:700]}, ensure_ascii=False)


def record_text(item: dict[str, Any]) -> str:
    """What is stored for an included record whose page is not fetched: its metadata and abstract."""
    lines = [f"Source: {item['url']}", "", f"# {item['title']}", ""]
    for label, value in (("Authors", ", ".join(item["authors"])), ("Date", item["date"]), ("Type", item["evidenceType"]),
                         ("Venue", item["extra"].get("venue")), ("DOI", item["doi"]), ("Found by", ", ".join(item["foundBy"]))):
        if value:
            lines.append(f"- {label}: {value}")
    lines += ["", "## Abstract", "", item["abstract"] or "(no abstract available)"]
    return "\n".join(lines)


def store_included(root: Path, topic: str, included: list[dict[str, Any]], append: bool = False) -> None:
    """Commit the text of every included record under sources/search-<topic>/: scholarly records and books as
    metadata and abstract (abstracts in v1), everything else as the fetched page, falling back to the metadata."""
    source_id = f"search-{topic}"[:60].strip("-")
    families = {identifier: spec["family"] for identifier, spec in registry.descriptors(root).items()}
    entries, texts = {}, {}
    for item in included:
        stored = f"{item['id'].lower()}-{ingest.url_slug(item['url'])}.md"
        text, extractor, data = record_text(item), "metadata", b""
        if families.get(item["adapter"]) not in ("scholarly", "books"):
            try:
                _, text, extractor, data = ingest.url_document(item["url"])
            except (extract.Skip, urllib.error.URLError, http.client.HTTPException, subprocess.TimeoutExpired, OSError, ValueError):
                text, extractor = record_text(item), "metadata"
        texts[stored] = text
        entries[stored] = {"origin": item["url"], "sha256": hashlib.sha256(data or text.encode()).hexdigest(), "extractor": extractor}
        item["stored"] = f"sources/{source_id}/text/{stored}"
    descriptor = {
        "schemaVersion": 1, "id": source_id, "kind": "url", "locators": [item["url"] for item in included],
        "include": [], "exclude": [], "depth": 0, "maxDocuments": len(included), "note": f"records included by research/{topic}",
        "origin": f"research:{topic}", "addedAt": rc.today(),
    }
    rc.write_json(ingest.source_path(root, source_id), descriptor)
    store_appending(root, descriptor, entries, texts, [], append)


def screen_check(batch: list[dict[str, Any]], criteria: dict[str, Any], known: set[str]):
    """The contract of one screener reply: one decision per record of the batch; an exclusion names a criterion,
    an inclusion the questions it bears on, and both give a reason."""
    wanted = {item["id"] for item in batch}

    def check(data: Any) -> dict[str, dict[str, Any]]:
        entries = data.get("decisions") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise ValueError('expected {"decisions": [{"id", "decision", "criterion", "questions", "reason"}]}')
        seen = {entry.get("id"): entry for entry in entries}
        problems = [f"no decision for {identifier}" for identifier in sorted(wanted - set(seen))]
        problems += [f"{identifier} is not in this batch" for identifier in sorted(set(seen) - wanted, key=str)]
        for identifier in sorted(wanted & set(seen)):
            entry = seen[identifier]
            if not str(entry.get("reason", "")).strip():
                problems.append(f"{identifier}: give a reason")
            if entry.get("decision") == "exclude":
                if entry.get("criterion") not in criteria:
                    problems.append(f"{identifier}: an exclusion names one of {sorted(criteria)}")
            elif entry.get("decision") == "include":
                if not entry.get("questions") or set(entry["questions"]) - known:
                    problems.append(f"{identifier}: an inclusion names the brief questions it bears on")
            else:
                problems.append(f"{identifier}: decision must be include or exclude")
        if problems:
            raise ValueError("; ".join(problems[:20]))
        return seen
    return check


def mark_retractions(session: rc.Session, root: Path, records: list[dict[str, Any]], log: Path) -> str:
    """Flag the records whose DOI a retraction-aware adapter (Crossref) lists as retracted, withdrawn or removed.
    Records that adapter found itself already carry the flag. Returns how the check went, for the screening log."""
    aware = {identifier for identifier, spec in registry.descriptors(root).items() if spec.get("retractions")}
    dois = [item["doi"] for item in records if item.get("doi") and not item["extra"].get("retracted") and not set(item["foundBy"]) & aware]
    if not dois:
        return "no DOIs to check"
    try:
        found = registry.retractions(root, dois, log)
    except kit.AdapterError as error:
        session.say(f"retraction check failed ({error}); these records were screened without it", "warn")
        return f"failed for {len(dois)} DOIs: {error}"
    for item in records:
        if item.get("doi") in found:
            item["extra"]["retracted"] = True
            item["extra"]["retractionNotices"] = found[item["doi"]]
    return f"{len(dois)} DOIs checked, {sum(item.get('doi') in found for item in records)} retracted"


def screen_hop(session: rc.Session, root: Path, topic: str, records: list[dict[str, Any]], hop: int,
               plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Decisions for one set of records: retracted ones excluded by the runner, the rest by the screener in batches."""
    config = rc.settings(root)
    criteria = {item["id"]: item for item in plan["exclusions"]}
    known = set(questions(root, topic))
    decisions: dict[str, dict[str, Any]] = {}
    for item in records:
        if item["extra"].get("retracted"):
            decisions[item["id"]] = {"decision": "exclude", "criterion": RETRACTED, "questions": [],
                                     "reason": "the publisher or the index flags it as retracted"}
    pending = [item for item in records if item["id"] not in decisions]
    size = config["research"].get("screenBatch", 40)
    batches = [pending[index:index + size] for index in range(0, len(pending), size)]
    criteria_text = "\n".join(f"- {item['id']}: {item['text']} (from the brief's {item['from']})" for item in plan["exclusions"])
    replies = session.parallel([
        (f"screen-{hop}-{number}", lambda number=number, batch=batch: session.call_checked(
            config["pipeline"]["screener"],
            f"# Task\n\nScreen these {len(batch)} candidate records for research/{topic}.\n\n{context(root, topic)}\n\n"
            f"# Exclusion criteria\n\n{criteria_text}\n\n# Candidates, one JSON object per line\n\n" + "\n".join(map(candidate_line, batch)),
            f"screen-{hop}-{number}", json_reply(screen_check(batch, criteria, known))))
        for number, batch in enumerate(batches, 1)
    ])
    for seen in replies.values():
        for identifier, entry in seen.items():
            decisions[identifier] = {"decision": entry["decision"], "criterion": entry.get("criterion") if entry["decision"] == "exclude" else None,
                                     "questions": entry.get("questions", []) if entry["decision"] == "include" else [],
                                     "reason": " ".join(str(entry["reason"]).split())}
    return decisions


def snowball(session: rc.Session, root: Path, frontier: list[dict[str, Any]], seen: set[str], next_number: int, hop: int,
             log: Path) -> tuple[list[dict[str, Any]], int]:
    """Follow the references (backward) and the citing works (forward) of the most cited included records.
    Returns the records not seen before, numbered on from next_number, and how many results the lookups gave."""
    config = rc.settings(root)["research"]
    followers = [identifier for identifier, spec in registry.descriptors(root).items() if spec.get("related")]
    if not followers:
        return [], 0
    seeds = sorted((item for item in frontier if item.get("doi") or item["extra"].get("openalexId")),
                   key=lambda item: -int(item["extra"].get("citedByCount") or 0))[: config.get("snowballSeeds", 5)]
    found: list[dict[str, Any]] = []
    for seed in seeds:
        for direction in kit.DIRECTIONS:
            try:
                results = registry.related(root, followers[0], seed, direction, config.get("snowballPerSeed", 10), log)
            except kit.AdapterError as error:
                session.say(f"snowball {seed['id']} {direction}: failed, {error}", "warn")
                continue
            found += [{**item, "via": f"{seed['id']} {direction}", "questions": seed["questions"]} for item in results]
    fresh = [item for item in registry.merge(found) if item["key"] not in seen]
    for offset, item in enumerate(fresh):
        item["id"] = f"R{next_number + offset}"
        item["hop"] = hop
        item["via"] = sorted({other["via"] for other in found if other["key"] == item["key"]})
        item["questions"] = sorted({question for other in found if other["key"] == item["key"] for question in other["questions"]})
    session.say(f"snowball hop {hop}: {len(found)} references and citations from {len(seeds)} key works, {len(fresh)} new")
    return fresh, len(found)


def stage_screen(session: rc.Session, root: Path, topic: str) -> None:
    """Screen the search candidates, then snowball: follow the references and citations of the key included works
    for research.snowballDepth hops, screening each hop the same way. Retractions are checked before every
    screening. Included records are stored for the researchers."""
    config = rc.settings(root)
    directory = topic_dir(root, topic)
    plan = rc.load_json(directory / "source-plan.json")
    candidates = rc.load_json(directory / "candidates.json")
    log = directory / "citations.json"
    log.unlink(missing_ok=True)
    records = [{**item, "hop": 0, "via": []} for item in candidates["records"]]
    checks = [mark_retractions(session, root, records, log)]
    decisions = screen_hop(session, root, topic, records, 0, plan)
    frontier = [item for item in records if decisions[item["id"]]["decision"] == "include"]
    citation_identified = 0
    for hop in range(1, config["research"].get("snowballDepth", 1) + 1):
        fresh, identified = snowball(session, root, frontier, {item["key"] for item in records}, len(records) + 1, hop, log)
        citation_identified += identified
        if not fresh:
            break
        checks.append(mark_retractions(session, root, fresh, log))
        decisions.update(screen_hop(session, root, topic, fresh, hop, plan))
        records += fresh
        frontier = [item for item in fresh if decisions[item["id"]]["decision"] == "include"]
    if not log.is_file():
        rc.write_json(log, [])
    included = [item for item in records if decisions[item["id"]]["decision"] == "include"]
    store_included(root, topic, included)
    stored = {item["id"]: item["stored"] for item in included}
    rows = [{"id": item["id"], "key": item["key"], "title": item["title"], "url": item["url"], "doi": item["doi"],
             "foundBy": item["foundBy"], "hop": item["hop"], "via": item["via"], "evidenceType": item["evidenceType"],
             "fingerprint": item["extra"].get("sha256"), **decisions[item["id"]], "stored": stored.get(item["id"])} for item in records]
    excluded_by: dict[str, int] = {}
    for row in rows:
        if row["decision"] == "exclude":
            excluded_by[row["criterion"]] = excluded_by.get(row["criterion"], 0) + 1
    searched = len(candidates["records"])
    flow = {"identified": candidates["identified"], "duplicates": candidates["identified"] - searched,
            "citationIdentified": citation_identified, "citationDuplicates": citation_identified - (len(records) - searched),
            "screened": len(records), "excluded": sum(excluded_by.values()), "excludedBy": dict(sorted(excluded_by.items())),
            "included": len(included)}
    rc.write_json(directory / "screening.json", {"flow": flow, "criteria": plan["exclusions"], "retractionCheck": checks, "records": rows})
    rc.write_text(directory / "screening.md", render_screening(topic, flow, plan["exclusions"], rows, checks))
    session.say(f"screen: {flow['included']} included, {flow['excluded']} excluded of {flow['screened']} candidates")


def flow_text(flow: dict[str, Any], criteria: list[dict[str, Any]]) -> str:
    """The PRISMA-style flow: identified by searching and by citation, duplicates, screened, excluded by criterion, included."""
    names = {item["id"]: item["text"] for item in criteria} | {RETRACTED: "retracted"}
    lines = [f"- Identified by adapter searches: {flow['identified']}", f"- Duplicates removed: {flow['duplicates']}"]
    if flow.get("citationIdentified"):
        lines += [f"- Identified by following references and citations: {flow['citationIdentified']}",
                  f"- Of those, duplicates or already found: {flow['citationDuplicates']}"]
    lines += [f"- Screened: {flow['screened']}", f"- Excluded: {flow['excluded']}"]
    lines += [f"  - {criterion} ({names.get(criterion, criterion)}): {count}" for criterion, count in flow["excludedBy"].items()]
    lines.append(f"- Included: {flow['included']}")
    return "\n".join(lines)


def render_screening(topic: str, flow: dict[str, Any], criteria: list[dict[str, Any]], rows: list[dict[str, Any]],
                     checks: list[str]) -> str:
    def found(row: dict[str, Any]) -> str:
        how = f"hop {row['hop']}: {', '.join(row['via'])}" if row["hop"] else f"search: {', '.join(row['foundBy'])}"
        return how + (f" (refresh {row['addedAt']}{', changed page' if row.get('changed') else ''})" if row.get("addedAt") else "")

    lines = [f"# Screening: {topic}\n", flow_text(flow, criteria), "", f"Retraction check: {'; '.join(checks)}.", "", "## Included\n",
             "Read these first: each record's text is stored at the path given.\n",
             "| Record | Title | Type | Found | Questions | Stored | Reason |", "| --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {row['id']} | [{cell(row['title'])}]({row['url']}) | {row['evidenceType']} | {cell(found(row))} | {', '.join(row['questions'])} | "
              f"{row['stored']} | {cell(row['reason'])} |" for row in rows if row["decision"] == "include"]
    lines += ["", "## Excluded\n", "| Record | Title | Found | Criterion | Reason |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {row['id']} | [{cell(row['title'])}]({row['url']}) | {cell(found(row))} | {row['criterion']} | {cell(row['reason'])} |"
              for row in rows if row["decision"] == "exclude"]
    return "\n".join(lines)


def cell(value: Any) -> str:
    """One Markdown table cell: a single line with pipes escaped (titles like "Pricing | Docs" break tables)."""
    return " ".join(str(value).split()).replace("|", "\\|")


def portable(root: Path, source_id: str) -> str:
    """How a handoff names an ingested source: its git remote or URLs, never a machine's local path."""
    manifest = ingest.read_manifest(root, source_id)
    if manifest.get("remote"):
        return manifest["remote"]
    urls = [locator for locator in manifest.get("locators", []) if "://" in locator]
    return " ".join(urls) or f"local {manifest.get('kind', 'source')}"


def normalized(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def quote_found(quote: str, text: str) -> bool:
    """True when a quote of at least MIN_QUOTE_WORDS words is in the stored page as whole words: entirely, or
    80% of its five-word runs (conversion reflows text). In the fuzzy case every run holding a number or a
    negation must match, so "improved by 7 points" never verifies against a page that says 2."""
    needle, haystack = normalized(quote), f" {normalized(text)} "
    words = needle.split()
    if len(words) < MIN_QUOTE_WORDS:
        return False
    if f" {needle} " in haystack:
        return True
    runs = [words[index:index + 5] for index in range(len(words) - 4)]
    found = [f" {' '.join(run)} " in haystack for run in runs]
    critical = [hit for run, hit in zip(runs, found) if any(word.isdigit() or word in NEGATIONS for word in run)]
    return all(critical) and sum(found) >= 0.8 * len(runs)


def source_key(url: str) -> str:
    """The identity a cited page merges on: its DOI when the URL is one, else the canonical URL (which keeps the
    query, so ?id=1 and ?id=2 stay different pages). The same keys as adapter records."""
    return kit.record_key(kit.bare_doi(url), url)


def included_records(root: Path, topic: str) -> dict[str, dict[str, Any]]:
    """The screened-in records of a topic by key; empty for a topic screened before the screen stage existed."""
    path = topic_dir(root, topic) / "screening.json"
    if not path.is_file():
        return {}
    return {row["key"]: row for row in rc.load_json(path)["records"] if row["decision"] == "include" and row.get("stored")}


def stage_collect(session: rc.Session, root: Path, topic: str, only: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Researchers read the included records and search the web; the runner stores every cited page and checks
    every quote. With only (a refresh), they read just those new records, without web search, and the sources
    and claims are appended to the ledger: existing ids never change. Returns the claims added."""
    config = rc.settings(root)
    known = set(questions(root, topic))
    limit = config["research"]["maxSourcesPerResearcher"]
    records = included_records(root, topic)
    types = evidence_types(root)

    def check(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict) or not isinstance(data.get("sources"), list) or not isinstance(data.get("claims"), list) \
                or not data["sources"] or not data["claims"]:
            raise ValueError("expected {\"sources\": [...], \"claims\": [...]} with at least one of each")
        # Web sources past the limit are dropped with the claims citing them before anything else is checked, so
        # the merge below never meets a claim whose source is gone. Included records never count against it.
        web = [source for source in data["sources"] if source_key(str(source.get("url", ""))) not in records]
        dropped = {id(source) for source in web[limit:]}
        kept = [source for source in data["sources"] if id(source) not in dropped]
        refs = {source.get("ref") for source in kept}
        everything = {source.get("ref") for source in data["sources"]}
        unknown = [claim for claim in data["claims"] if claim.get("source") not in everything]
        if unknown:
            raise ValueError(f"claim {unknown[0].get('text', '')[:60]!r} cites unknown source {unknown[0].get('source')}")
        data = {**data, "sources": kept, "claims": [claim for claim in data["claims"] if claim.get("source") in refs],
                "overLimit": len(data["sources"]) - len(kept)}
        if not data["claims"]:
            raise ValueError(f"no claim cites one of the first {limit} sources; list at most {limit} sources")
        for source in data["sources"]:
            if not str(source.get("url", "")).startswith(("http://", "https://")):
                raise ValueError(f"source {source.get('ref')} needs an http(s) url")
            if source.get("evidenceType") not in types:
                raise ValueError(f"source {source.get('ref')}: evidenceType must be one of {sorted(types)}")
            if source.get("reliability") not in GRADES or not str(source.get("reliabilityReason", "")).strip():
                raise ValueError(f"source {source.get('ref')}: reliability is one of {GRADES} with a reliabilityReason")
        for claim in data["claims"]:
            if not claim.get("text") or not claim.get("quote"):
                raise ValueError(f"claim {claim.get('text', '')[:60]!r} needs text and a verbatim quote")
            if set(claim.get("questions", [])) - known:
                raise ValueError(f"claim {claim.get('text', '')[:60]!r} refers to unknown questions")
            if claim.get("via") is not None and not str(claim["via"]).strip():
                raise ValueError(f"claim {claim.get('text', '')[:60]!r}: via names the original source, or is left out")
        return data

    if only is None:
        body = (
            f"# Task\n\nCollect evidence for research/{topic}. First read the included records listed in research/{topic}/screening.md "
            f"(their text is stored at the paths given) and extract claims from them, citing each by its URL. Then search the web along "
            f"the `web` avenues of research/{topic}/source-plan.md for what the records leave open. At most {limit} web sources; "
            f"included records do not count.\n\n{context(root, topic)}"
        )
    else:
        listing = "\n".join(f"- {row['id']}: {row['title']} | {row['url']} | stored at {row['stored']}" for row in only)
        body = (
            f"# Task\n\nA refresh of research/{topic} found new records. Read only these, extract claims from them and cite each by "
            f"its URL. Do not search the web: the existing ledger (research/{topic}/claims.md) already covers the rest; note where a new "
            f"record contradicts or updates it.\n\nNew records:\n{listing}\n\n{context(root, topic)}"
        )
    researchers = config["pipeline"]["researchers"]
    replies = session.parallel([
        (role_id, lambda role_id=role_id: session.call_checked(role_id, body, f"collect-{role_id}", json_reply(check)))
        for role_id in researchers
    ])

    # Merge sources across researchers (and with the existing ledger on a refresh) by key, then store each new page
    # so every claim has committed evidence.
    existing = ledger(root, topic) if only is not None else {"sources": [], "claims": []}
    merged: dict[str, dict[str, Any]] = {source_key(source["url"]): source for source in existing["sources"]}
    version = topic_version(topic_dir(root, topic))
    claims: list[dict[str, Any]] = []
    for role_id in researchers:
        reply = replies[role_id]
        if reply["overLimit"]:
            session.say(f"collect-{role_id}: {reply['overLimit']} sources past the limit of {limit} dropped with their claims", "warn")
        local = {}
        for source in reply["sources"]:
            key = source_key(source["url"])
            evidence = records[key]["evidenceType"] if key in records else source["evidenceType"]
            ceiling = types[evidence]["reliabilityCeiling"]
            entry = merged.setdefault(key, {
                "id": f"S{len(merged) + 1}", "url": source["url"], "title": source.get("title", ""),
                "published": source.get("published", "unknown"), "evidenceType": evidence,
                "reliability": capped(source["reliability"], ceiling), "reliabilityReason": " ".join(str(source["reliabilityReason"]).split()),
                "foundBy": [], "addedIn": version, "checkedAt": rc.today(),
            })
            if capped(source["reliability"], ceiling) != source["reliability"]:
                entry["reliabilityCapped"] = f"{role_id} said {source['reliability']}; {evidence} is at best {ceiling}"
            if key in records:
                entry["record"] = records[key]["id"]
            entry["foundBy"] = sorted(set(entry["foundBy"]) | {role_id})
            local[source["ref"]] = entry["id"]
        for claim in reply["claims"]:
            claims.append({
                "text": " ".join(claim["text"].split()), "source": local[claim["source"]], "quote": " ".join(claim["quote"].split()),
                "questions": claim.get("questions", []), "type": claim.get("type", "fact"), "foundBy": role_id, "addedIn": version,
                **({"via": " ".join(str(claim["via"]).split())} if claim.get("via") else {}),
            })

    source_id = f"web-{topic}"[:60].strip("-")
    entries, texts, skipped = {}, {}, []
    for entry in merged.values():
        if "fetch" in entry:
            continue  # stored by an earlier version of this topic
        if entry.get("record"):
            # Already screened in and stored; the claim is checked against that text, not a second download.
            entry["fetch"], entry["stored"] = "ok", records[source_key(entry["url"])]["stored"]
            continue
        try:
            stored, text, extractor, data = ingest.url_document(entry["url"])
        # One unreadable page is recorded and skipped; it never fails a stage whose replies are already paid for.
        except (extract.Skip, urllib.error.URLError, http.client.HTTPException, subprocess.TimeoutExpired, OSError, ValueError) as reason:
            entry["fetch"] = f"failed: {str(reason)[:160]}"
            entry["stored"] = None
            skipped.append({"origin": entry["url"], "reason": entry["fetch"]})
            continue
        texts[stored] = text
        entries[stored] = {"origin": entry["url"], "sha256": hashlib.sha256(data).hexdigest(), "extractor": extractor}
        entry["fetch"] = "ok"
        entry["stored"] = f"sources/{source_id}/text/{stored}"
    descriptor = {
        "schemaVersion": 1, "id": source_id, "kind": "url", "locators": [entry["url"] for entry in merged.values() if not entry.get("record")],
        "include": [], "exclude": [], "depth": 0, "maxDocuments": len(merged), "note": f"pages cited by research/{topic}",
        "origin": f"research:{topic}", "addedAt": rc.today(),
    }
    rc.write_json(ingest.source_path(root, source_id), descriptor)
    store_appending(root, descriptor, entries, texts, skipped, append=only is not None)

    sources_by_id = {entry["id"]: entry for entry in merged.values()}
    for number, claim in enumerate(claims, len(existing["claims"]) + 1):
        claim["id"] = f"C{number}"
        stored = sources_by_id[claim["source"]].get("stored")
        claim["quoteVerified"] = bool(stored) and quote_found(claim["quote"], (root / stored).read_text(encoding="utf-8"))
        if claim.get("via"):
            # SIFT: a claim reported second-hand is traced when its original is itself in the ledger.
            claim["traced"] = any(source_key(url.rstrip(".,;)")) in merged for url in re.findall(r"https?://\S+", claim["via"]))
    added = [{"id": claim.pop("id"), **claim} for claim in claims]
    led = {"topic": topic, "sources": list(merged.values()), "claims": [*existing["claims"], *added]}
    directory = topic_dir(root, topic)
    rc.write_json(directory / "claims.json", led)
    rc.write_text(directory / "claims.md", render_ledger(led))
    fetched = sum(entry.get("fetch") == "ok" for entry in merged.values())
    verified = sum(claim["quoteVerified"] for claim in added)
    session.say(f"collect: {len(added)} claims added, {len(led['claims'])} in the ledger from {len(merged)} sources ({fetched} stored); "
                f"{verified} of the new quotes verified")
    return added


def store_appending(root: Path, descriptor: dict[str, Any], entries: dict[str, Any], texts: dict[str, str],
                    skipped: list[dict[str, str]], append: bool) -> None:
    """ingest.store, which replaces a source's files; with append, the files an earlier version stored are kept."""
    if append:
        previous = ingest.read_manifest(root, descriptor["id"]).get("files", {})
        text_root = root / "sources" / descriptor["id"] / "text"
        for stored, entry in previous.items():
            if stored not in entries and (text_root / stored).is_file():
                entries[stored] = {key: value for key, value in entry.items() if key != "redactions"}
                texts[stored] = (text_root / stored).read_text(encoding="utf-8")
        descriptor["locators"] = sorted(set(descriptor["locators"]) | {entry["origin"] for entry in entries.values()})
    ingest.store(root, descriptor, entries, texts, skipped, {})


def render_ledger(ledger: dict[str, Any]) -> str:
    sources = {source["id"]: source for source in ledger["sources"]}
    lines = [f"# Claims ledger: {ledger['topic']}\n", "A claim whose quote is not verified, or whose page could not be stored, "
             "rests on the researcher's word alone. A drifted claim's page no longer says what was quoted.\n",
             "| Claim | Text | Source | Reliability | Quote verified | Via | Questions |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for claim in ledger["claims"]:
        source = sources[claim["source"]]
        where = source.get("stored") or f"{source['url']} (not stored)"
        verified = "drifted" if claim.get("drifted") else "yes" if claim["quoteVerified"] else "no"
        via = f"{cell(claim['via'])} ({'traced' if claim.get('traced') else 'not traced'})" if claim.get("via") else ""
        lines.append(f"| {claim['id']} | {cell(claim['text'])} | {source['id']}: {cell(where)} | {source.get('reliability', '?')} | "
                     f"{verified} | {via} | {', '.join(claim['questions'])} |")
    lines += ["", "## Sources", ""]
    lines += [f"- {source['id']}: [{source.get('title') or source['url']}]({source['url']}) ({source.get('evidenceType', source.get('kind', '?'))}, "
              f"reliability {source.get('reliability', '?')}: {source.get('reliabilityReason', 'not graded')}; published {source['published']}) "
              f"stored: {source.get('stored') or source.get('fetch')}" for source in ledger["sources"]]
    return "\n".join(lines)


def ledger(root: Path, topic: str) -> dict[str, Any]:
    return rc.load_json(topic_dir(root, topic) / "claims.json")


def stage_analyze(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    claim_ids = {claim["id"] for claim in ledger(root, topic)["claims"]}
    known = set(questions(root, topic))
    plan = rc.load_json(topic_dir(root, topic) / "source-plan.json")

    def check(reply: str) -> tuple[str, dict[str, Any]]:
        ideas = rc.extract_json(reply)
        if not isinstance(ideas, dict) or not ideas.get("ideas"):
            raise ValueError("end with a ```json block {\"ideas\": [{\"id\": \"I1\", \"name\", \"summary\", \"claims\": [...]}]}")
        markdown = re.sub(r"```json\s*\n.*?\n```\s*\Z", "", reply.strip(), flags=re.DOTALL).strip()
        unknown = set(claim_refs(markdown)) - claim_ids
        for idea in ideas["ideas"]:
            if not IDEA_ID.fullmatch(str(idea.get("id", ""))) or not idea.get("name"):
                raise ValueError(f"idea {idea} needs an id like I1 and a name")
            unknown |= set(idea.get("claims", [])) - claim_ids
        if unknown:
            raise ValueError(f"cites claims that are not in the ledger: {sorted(unknown)}")
        missing = [question for question in sorted(known) if not re.search(rf"\b{question}\b", markdown)]
        if missing:
            raise ValueError(f"does not answer {missing}: give each question its own section")
        problems = analysis_problems(ideas, sorted(known, key=lambda value: int(value[1:])), claim_ids, plan)
        if problems:
            raise ValueError("; ".join(problems[:20]))
        return markdown, ideas

    body = f"# Task\n\nAnswer the brief's questions from research/{topic}/claims.md.\n\n{context(root, topic)}"
    if (topic_dir(root, topic) / "ideas.json").is_file():
        # A refresh: the ledger grew. Keep the ids of ideas that are still the same idea, so their history continues.
        previous = rc.load_json(topic_dir(root, topic) / "ideas.json")["ideas"]
        body += ("\n\n# Previous version\n\nThe ledger has new claims since the last analysis. Its ideas were:\n"
                 + "\n".join(f"- {idea['id']}: {idea['name']}" for idea in previous)
                 + "\nKeep an idea's id when it is still the same idea, even if the evidence now weakens it; give new ideas new ids.")
    competing = {question: plan_hypotheses(plan, question) for question in sorted(known) if len(plan_hypotheses(plan, question)) > 1}
    if competing:
        body += ("\n\n# Competing hypotheses\n\nThe plan weighs these against each other; give each such question an ach matrix:\n"
                 + "\n".join(f"- {question}: {', '.join(hypotheses)}" for question, hypotheses in competing.items()))
    markdown, ideas = session.call_checked(config["pipeline"]["analyst"], body, "analyze", check)
    directory = topic_dir(root, topic)
    rc.write_text(directory / "analysis.md", markdown + "\n\n" + render_structure(ideas, plan))
    rc.write_json(directory / "ideas.json", ideas)


def render_structure(ideas: dict[str, Any], plan: dict[str, Any]) -> str:
    """The analysis's assumptions and matrices as tables, appended by the runner so sceptics review them too.
    Claim ids are written bare: these tables are not citations."""
    statements = {item["id"]: item["statement"] for item in plan.get("hypotheses", [])}
    lines = ["## Assumptions and competing hypotheses (from the analysis's data)", ""]
    for entry in ideas.get("questions", []):
        lines += [f"### {entry['question']}", ""]
        lines += [f"- {item['id']}: {item['text']}" + (f" (rests on {', '.join(item['claims'])})" if item.get("claims") else "")
                  for item in entry.get("assumptions", [])]
        ach = entry.get("ach")
        if ach:
            lines += ["", "| Claim | " + " | ".join(ach["hypotheses"]) + " |", "| --- |" + " --- |" * len(ach["hypotheses"])]
            lines += [f"| {row['claim']} | " + " | ".join(row["ratings"][hypothesis] for hypothesis in ach["hypotheses"]) + " |" for row in ach["matrix"]]
            lines += [""] + [f"- {hypothesis}: {statements.get(hypothesis, '')}" for hypothesis in ach["hypotheses"]]
            lines += [f"- Untested alternative: {item}" for item in ach.get("untested", [])]
        lines.append("")
    return "\n".join(lines).rstrip()


def cited_claims(root: Path, topic: str) -> list[str]:
    directory = topic_dir(root, topic)
    cited = set(claim_refs((directory / "analysis.md").read_text(encoding="utf-8")))
    data = rc.load_json(directory / "ideas.json")
    for idea in data["ideas"]:
        cited |= set(idea.get("claims", []))
    # Claims weighed in a matrix or holding up an assumption are relied on too, so they are critiqued.
    for entry in data.get("questions", []):
        cited |= {claim for item in entry.get("assumptions", []) for claim in item.get("claims", [])}
        cited |= {row["claim"] for row in (entry.get("ach") or {}).get("matrix", [])}
    return sorted(cited, key=lambda value: int(value[1:]))


def assumptions_of(root: Path, topic: str) -> list[dict[str, Any]]:
    data = rc.load_json(topic_dir(root, topic) / "ideas.json")
    return [{**item, "question": entry["question"]} for entry in data.get("questions", []) for item in entry.get("assumptions", [])]


def stage_critique(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    wanted = cited_claims(root, topic)
    assumptions = [item["id"] for item in assumptions_of(root, topic)]

    def check(data: Any) -> dict[str, Any]:
        verdicts = data.get("claims") if isinstance(data, dict) else None
        if not isinstance(verdicts, list):
            raise ValueError("expected {\"claims\": [{\"claim\", \"verdict\", \"reason\", \"evidence\"}], \"assumptions\": [...], \"analysis\": [...]}")
        seen = {item.get("claim") for item in verdicts}
        missing = sorted(set(wanted) - seen, key=lambda value: int(value[1:]))
        bad = [item for item in verdicts if item.get("verdict") not in CLAIM_VERDICTS or not item.get("reason")]
        tested = {item.get("assumption"): item for item in data.get("assumptions", []) if isinstance(item, dict)}
        missing += [f"assumption {identifier}" for identifier in assumptions if identifier not in tested]
        bad += [item for item in tested.values() if item.get("verdict") not in CLAIM_VERDICTS or not item.get("reason")]
        if missing or bad:
            raise ValueError(f"missing verdicts for {missing}; invalid entries {bad[:3]} (verdict one of {CLAIM_VERDICTS} with a reason)")
        return data

    body = (
        f"# Task\n\nTry to disprove the claims that research/{topic}/analysis.md and ideas.json rely on: {', '.join(wanted)}"
        + (f"; and test the assumptions the answers rest on: {', '.join(assumptions)}" if assumptions else "")
        + f". The ledger is research/{topic}/claims.md; stored pages are under sources/.\n\n{context(root, topic)}"
    )
    sceptics = config["pipeline"]["sceptics"]
    reviews = session.parallel([
        (role_id, lambda role_id=role_id: session.call_checked(role_id, body, f"critique-{role_id}", json_reply(check)))
        for role_id in sceptics
    ])
    # Committed reviews carry neutral labels; who wrote which stays in the ignored run state.
    labels = list(string.ascii_lowercase[: len(sceptics)])
    random.shuffle(labels)
    directory = topic_dir(root, topic) / "critique"
    if directory.exists():
        shutil.rmtree(directory)
    mapping = {}
    for role_id, label in zip(sceptics, labels):
        rc.write_json(directory / f"review-{label}.json", reviews[role_id])
        mapping[label] = role_id
    rc.write_json(root / ".rc-local" / "research" / topic / "reviewers.json", mapping)


def stage_judge(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    directory = topic_dir(root, topic)
    wanted = cited_claims(root, topic)
    ideas = [idea["id"] for idea in rc.load_json(directory / "ideas.json")["ideas"]]
    reviews = {path.stem.removeprefix("review-").upper(): rc.load_json(path) for path in sorted((directory / "critique").glob("review-*.json"))}
    claim_ids = {claim["id"] for claim in ledger(root, topic)["claims"]}
    assumptions = [item["id"] for item in assumptions_of(root, topic)]

    def check(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("expected {\"claims\": [...], \"ideas\": [...], \"assumptions\": [...], \"answers\": [...]}")
        claim_seen = {item.get("claim"): item for item in data.get("claims", [])}
        idea_seen = {item.get("idea"): item for item in data.get("ideas", [])}
        problems = [f"no verdict for {claim}" for claim in wanted if claim not in claim_seen]
        problems += [f"no verdict for idea {idea}" for idea in ideas if idea not in idea_seen]
        problems += [f"{key}: verdict must be one of {CLAIM_VERDICTS}" for key, item in claim_seen.items() if item.get("verdict") not in CLAIM_VERDICTS]
        problems += [f"{key}: verdict must be one of {IDEA_VERDICTS}" for key, item in idea_seen.items() if item.get("verdict") not in IDEA_VERDICTS]
        problems += [f"{key}: credibility must be one of {CREDIBILITY}" for key, item in claim_seen.items()
                     if item.get("credibility") not in CREDIBILITY]
        problems += answer_problems(data.get("answers"), questions(root, topic), claim_ids)
        settled = {item.get("assumption"): item for item in data.get("assumptions", []) if isinstance(item, dict)}
        problems += [f"no verdict for assumption {identifier}" for identifier in assumptions if identifier not in settled]
        problems += [f"assumption {key}: verdict must be one of {CLAIM_VERDICTS}" for key, item in settled.items()
                     if item.get("verdict") not in CLAIM_VERDICTS]
        if problems:
            raise ValueError("; ".join(problems[:20]))
        return data

    shown = "\n\n".join(f"## Review {label}\n\n```json\n{json.dumps(review, ensure_ascii=False, indent=1)[:60000]}\n```"
                        for label, review in reviews.items())
    body = (
        f"# Task\n\nSettle every claim ({', '.join(wanted)}) and idea ({', '.join(ideas)}) of research/{topic}/analysis.md "
        f"and ideas.json from these anonymous reviews, checking them against the stored sources"
        + (f"; settle the assumptions ({', '.join(assumptions)})" if assumptions else "")
        + f". Then grade the certainty of the answer to each question ({', '.join(questions(root, topic))}).\n\n{context(root, topic)}\n\n{shown}"
    )
    data = session.call_checked(config["pipeline"]["judge"], body, "judge", json_reply(check))
    # A claim one reviewer refuted but the judge kept is contested: the report says so; only the user can settle it.
    contested = []
    for item in data["claims"]:
        refuted_by = [label for label, review in reviews.items()
                      if any(entry.get("claim") == item["claim"] and entry.get("verdict") == "REFUTED" for entry in review.get("claims", []))]
        if refuted_by and item["verdict"] in ("HOLDS", "WEAK"):
            contested.append({"claim": item["claim"], "refutedBy": [f"Review {label}" for label in refuted_by]})
    data["contested"] = contested
    previous = rc.load_json(directory / "judgement.json") if (directory / "judgement.json").is_file() else {}
    data["claims"] = with_history(data["claims"], previous.get("claims", []), "claim", "verdict", topic_version(directory))
    data["ideas"] = with_history(data["ideas"], previous.get("ideas", []), "idea", "verdict", topic_version(directory))
    rc.write_json(directory / "judgement.json", data)
    lines = [f"# Judgement: {topic}\n", "## Certainty of the answers\n", certainty_text(data["answers"]), "",
             "| Claim | Verdict | Credibility | Reason |", "| --- | --- | --- | --- |"]
    lines += [f"| {item['claim']} | {item['verdict']}{' (earlier version)' if item.get('carried') else ''} | {item.get('credibility', '?')} | "
              f"{cell(item.get('reason', ''))} |" for item in data["claims"]]
    lines += ["", "| Idea | Verdict | Reason |", "| --- | --- | --- |"]
    lines += [f"| {item['idea']} | {item['verdict']} | {cell(item.get('reason', ''))} |" for item in data["ideas"]]
    if contested:
        lines += ["", "## Contested", ""] + [f"- {item['claim']}: refuted by {', '.join(item['refutedBy'])}, kept by the judge" for item in contested]
    rc.write_text(directory / "judgement.md", "\n".join(lines))


def certainty_text(answers: list[dict[str, Any]]) -> str:
    """One line per question: its certainty and why it is not higher."""
    lines = []
    for item in sorted(answers, key=lambda answer: int(answer["question"][1:])):
        reasons = [f"{entry['domain']} -{entry.get('levels', 1)}: {entry['reason']}" for entry in item.get("downgrades", [])]
        reasons += [f"{entry['domain']} +{entry.get('levels', 1)}: {entry['reason']}" for entry in item.get("upgrades", [])]
        lines.append(f"- {item['question']}: **{item['certainty']}**" + (f" ({'; '.join(reasons)})" if reasons else ""))
    return "\n".join(lines)


def topic_version(directory: Path) -> int:
    """The version a run or refresh is producing: watch.json's, or 1 for a topic that is not living (yet)."""
    path = directory / "watch.json"
    return rc.load_json(path)["version"] if path.is_file() else 1


def with_history(items: list[dict[str, Any]], previous: list[dict[str, Any]], key: str, field: str, version: int) -> list[dict[str, Any]]:
    """items, each carrying its earlier history plus today's value; earlier items not settled this time are kept
    as they were, marked carried. A full re-run starts over (ids change), a refresh continues the history."""
    before = {item[key]: item for item in previous}
    result = []
    for item in items:
        history = [entry for entry in before.get(item[key], {}).get("history", []) if entry.get("version") != version]
        result.append({**item, "history": [*history, {"version": version, "date": rc.today(), field: item[field]}]})
    settled = {item[key] for item in items}
    result += [{**item, "carried": True} for item in previous if item[key] not in settled]
    return result


def surviving_ideas(root: Path, topic: str) -> list[dict[str, Any]]:
    directory = topic_dir(root, topic)
    verdicts = {item["idea"]: item for item in rc.load_json(directory / "judgement.json")["ideas"]}
    return [{**idea, "verdict": verdicts[idea["id"]]["verdict"]} for idea in rc.load_json(directory / "ideas.json")["ideas"]
            if verdicts.get(idea["id"], {}).get("verdict") != "FALLS"]


def stage_apply(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    directory = topic_dir(root, topic)
    ideas = surviving_ideas(root, topic)
    owned = {item["id"] for item in ingest.sources(root) if item.get("origin", "user") == "user"}
    claim_ids = {claim["id"] for claim in ledger(root, topic)["claims"]}
    if not ideas:
        rc.write_json(directory / "fit.json", {"fits": []})
        rc.write_text(directory / "fit.md", f"# Fit: {topic}\n\nNo idea survived the critique, so nothing is applied.")
        (directory / "handoff.md").unlink(missing_ok=True)
        return

    def check(data: Any) -> dict[str, Any]:
        fits = data.get("fits") if isinstance(data, dict) else None
        if not isinstance(fits, list):
            raise ValueError("expected {\"fits\": [...]}")
        problems = [f"no fit for {idea['id']}" for idea in ideas if idea["id"] not in {fit.get("idea") for fit in fits}]
        for fit in fits:
            if fit.get("ring") not in RINGS or fit.get("effort") not in EFFORTS:
                problems.append(f"{fit.get('idea')}: ring must be one of {RINGS} and effort one of {EFFORTS}")
            unknown = set(fit.get("sources", [])) - owned
            if unknown:
                problems.append(f"{fit.get('idea')}: sources {sorted(unknown)} are not ingested sources")
            text = json.dumps(fit)
            problems += [f"{fit.get('idea')}: cites missing {path}" for path in ingest.CITATION.findall(text) if not (root / path).is_file()]
            problems += [f"{fit.get('idea')}: cites unknown claim {claim}" for claim in set(claim_refs(text)) - claim_ids]
            if not fit.get("rationale"):
                problems.append(f"{fit.get('idea')}: rationale is empty")
        if problems:
            raise ValueError("; ".join(problems[:20]))
        return data

    listing = "\n".join(f"- {idea['id']} ({idea['verdict']}): {idea['name']}: {idea.get('summary', '')}" for idea in ideas)
    body = (
        f"# Task\n\nAssess how each surviving idea fits the user's or company's needs and repos.\n\nIdeas:\n{listing}\n\n"
        f"Analysis: research/{topic}/analysis.md. Judgement: research/{topic}/judgement.md.\n\n{context(root, topic)}"
    )
    data = session.call_checked(config["pipeline"]["applier"], body, "apply", json_reply(check))
    previous = rc.load_json(directory / "fit.json")["fits"] if (directory / "fit.json").is_file() else []
    data["fits"] = [fit for fit in with_history(data["fits"], previous, "idea", "ring", topic_version(directory)) if not fit.get("carried")]
    rc.write_json(directory / "fit.json", data)
    names = {idea["id"]: idea["name"] for idea in ideas}
    lines = [f"# Fit: {topic}\n", "| Idea | Ring | Effort | Sources touched | Replaces |", "| --- | --- | --- | --- | --- |"]
    for fit in data["fits"]:
        lines.append(f"| {fit['idea']}: {cell(names.get(fit['idea'], ''))} | {fit['ring']} | {fit['effort']} | "
                     f"{', '.join(fit.get('sources', [])) or '-'} | {cell(fit.get('replaces', '-'))} |")
    for fit in data["fits"]:
        lines += ["", f"## {fit['idea']}: {names.get(fit['idea'], '')} ({fit['ring']})", "", fit["rationale"].strip()]
        if fit.get("risks"):
            lines += ["", f"Risks: {fit['risks']}"]
        if fit.get("nextStep"):
            lines += ["", f"Next step: {fit['nextStep']}"]
    rc.write_text(directory / "fit.md", "\n".join(lines))
    chosen = [fit for fit in data["fits"] if fit["ring"] in ("ADOPT", "TRIAL")]
    if chosen:
        rc.write_text(directory / "handoff.md", handoff(root, topic, chosen, names))
    else:
        (directory / "handoff.md").unlink(missing_ok=True)


def handoff(root: Path, topic: str, chosen: list[dict[str, Any]], names: dict[str, str]) -> str:
    """A Control Center task plan (templates/task-plan.md, the CC's own format) for the ideas worth acting on.
    The RC never writes into a CC: the user copies this into the CC's plans/active and grills it there."""
    title = (topic_dir(root, topic) / "brief.md").read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
    plan_id = f"rc-{topic}"[:60].strip("-")
    text = (root / "templates" / "task-plan.md").read_text(encoding="utf-8")
    text = text.replace("<task-id>", plan_id).replace("<outcome>", f"apply the research '{title}'")

    def fill(heading: str, body: str) -> None:
        nonlocal text
        text = text.replace(f"## {heading}\n", f"## {heading}\n\n{body.strip()}\n", 1)

    fill("Outcome", "\n".join(f"- {fit['idea']}: {names.get(fit['idea'], '')} ({fit['ring']}, effort {fit['effort']}). "
                              f"{' '.join(str(fit.get('nextStep', '')).split())}" for fit in chosen))
    fill("Non-goals", "Ideas the research ranked ASSESS or HOLD, and everything outside the research brief's scope.")
    fill("Evidence and current behavior", f"From the Research Center: research/{topic}/report.md, fit.md and claims.md "
         "(every claim there is cited and judged). Copy the relevant facts here while grilling; do not link to a path the CC cannot read.")
    rows = []
    for fit in chosen:
        for source in fit.get("sources", []):
            rows.append(f"| {source} ({cell(portable(root, source))}) | to decide | to decide | {cell(names.get(fit['idea'], ''))} |")
    text = text.replace("| --- | --- | --- | --- |\n\n## Invariants", "| --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n## Invariants", 1)
    fill("Invariants and decisions", "\n".join(f"- {fit['idea']}: {' '.join(str(fit['rationale']).split())}" for fit in chosen))
    question_rows = [f"| Risks of {fit['idea']}: {cell(fit.get('risks', 'not stated'))} | to assess | grill-task-planning |" for fit in chosen]
    text = text.replace("| --- | --- | --- |\n\n## Work packages", "| --- | --- | --- |\n" + "\n".join(question_rows) + "\n\n## Work packages", 1)
    return text


def stage_report(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    directory = topic_dir(root, topic)
    led = ledger(root, topic)
    judgement = rc.load_json(directory / "judgement.json")
    verdicts = {item["claim"]: item["verdict"] for item in judgement["claims"]}
    known = questions(root, topic)

    def check(reply: str) -> str:
        markdown = re.sub(r"\A---\n.*?\n---\n", "", reply.strip(), flags=re.DOTALL).strip()
        cited = set(claim_refs(markdown))
        problems = [f"cites {claim}, which is not in the ledger" for claim in sorted(cited) if claim not in {c["id"] for c in led["claims"]}]
        problems += [f"relies on {claim}, judged {verdicts[claim]}: drop it or name it as refuted outside a [C#] citation"
                     for claim in sorted(cited) if verdicts.get(claim) in ("REFUTED", "UNSUPPORTED")]
        problems += [f"does not answer {question}" for question in known if not re.search(rf"^## {question}\b", markdown, flags=re.MULTILINE)]
        if not cited:
            problems.append("cites no claim: every finding needs a [C#] citation")
        problems += language_problems(markdown, {item["question"]: item["certainty"] for item in judgement.get("answers", [])})
        if problems:
            raise ValueError("; ".join(problems[:20]))
        return markdown

    body = (
        f"# Task\n\nWrite the report for research/{topic}: read brief.md, analysis.md, ideas.json, judgement.md and fit.md there.\n\n"
        f"{context(root, topic)}"
    )
    markdown = session.call_checked(config["pipeline"]["reporter"], body, "report", check)
    sources = {source["id"]: source for source in led["sources"]}
    claims = {claim["id"]: claim for claim in led["claims"]}
    used = sorted(set(claim_refs(markdown)), key=lambda value: int(value[1:]))
    credibility = {item["claim"]: item.get("credibility", "?") for item in judgement["claims"]}
    appendix = []
    if judgement.get("answers"):
        appendix += ["", "## Certainty of the answers", "", "How sure each answer is, starting from high and lowered for each "
                     "named weakness of its evidence:", "", certainty_text(judgement["answers"])]
    structure = rc.load_json(directory / "ideas.json").get("questions", [])
    statements = {item["id"]: item["statement"] for item in rc.load_json(directory / "source-plan.json").get("hypotheses", [])}
    for entry in structure:
        if not entry.get("ach"):
            continue
        ranking, diagnostic = ach_ranking(entry["ach"], verdicts)
        appendix += ["", f"## Competing hypotheses for {entry['question']}", "",
                     "Ranked by how much surviving evidence is inconsistent with each, fewest first (Analysis of Competing Hypotheses):", ""]
        appendix += [f"{rank}. {hypothesis}: {statements.get(hypothesis, '')} ({count} inconsistent)" for rank, (hypothesis, count) in enumerate(ranking, 1)]
        appendix += ["", f"Diagnostic claims, the ones that tell the hypotheses apart: {', '.join(diagnostic) or 'none'}."]
        appendix += [f"Untested alternative (no search looked for evidence against it): {item}" for item in entry["ach"].get("untested", [])]
    settled = {item["assumption"]: item for item in judgement.get("assumptions", [])}
    assumed = [item for entry in structure for item in entry.get("assumptions", [])]
    if assumed:
        appendix += ["", "## Key assumptions", "", "| Assumption | Question | Verdict | Reason |", "| --- | --- | --- | --- |"]
        appendix += [f"| {item['id']}: {cell(item['text'])} | {entry['question']} | {settled.get(item['id'], {}).get('verdict', 'not judged')} | "
                     f"{cell(settled.get(item['id'], {}).get('reason', ''))} |" for entry in structure for item in entry.get("assumptions", [])]
    appendix += ["", "## Evidence", "", "Reliability of the source: A completely reliable to E unreliable, F cannot be judged. "
                 "Credibility of the claim: 1 confirmed to 5 improbable, 6 cannot be judged.", "",
                 "| Claim | Verdict | Credibility | Reliability | Quote verified | Source |", "| --- | --- | --- | --- | --- | --- |"]
    for claim_id in used:
        claim, source = claims[claim_id], sources[claims[claim_id]["source"]]
        verified = "drifted" if claim.get("drifted") else "yes" if claim["quoteVerified"] else "no"
        appendix.append(f"| {claim_id} | {verdicts.get(claim_id, 'not judged')} | {credibility.get(claim_id, '?')} | {source.get('reliability', '?')} | "
                        f"{verified} | [{cell(source.get('title') or source['url'])}]({source['url']}){' — ' + source['stored'] if source.get('stored') else ''} |")
    if (directory / "screening.json").is_file():
        screening = rc.load_json(directory / "screening.json")
        web = [source for source in led["sources"] if not source.get("record")]
        appendix += ["", "## How the sources were found", "", flow_text(screening["flow"], screening["criteria"]),
                     f"- Found by the researchers' web search: {len(web)} pages, {sum(source.get('stored') is not None for source in web)} stored",
                     "", f"Every search with its exact query: research/{topic}/searches.json. Every screening decision with its reason: "
                     f"research/{topic}/screening.md."]
    dropped = [item for item in judgement["claims"] if item["verdict"] in ("REFUTED", "UNSUPPORTED")]
    if dropped:
        appendix += ["", "## Refuted or unsupported", ""]
        appendix += [f"- {item['claim']} ({item['verdict']}): {claims[item['claim']]['text']} — {' '.join(str(item.get('reason', '')).split())}"
                     for item in dropped if item["claim"] in claims]
    if judgement.get("contested"):
        appendix += ["", "## Contested", "", "A reviewer refuted these claims and the judge kept them; settle them before acting:", ""]
        appendix += [f"- {item['claim']}: {claims[item['claim']]['text']}" for item in judgement["contested"] if item["claim"] in claims]
    if (directory / "handoff.md").is_file():
        appendix += ["", "## Handoff", "", f"research/{topic}/handoff.md is a Control Center task plan for the ideas ranked ADOPT or TRIAL: "
                     "copy it into the CC's plans/active and refine it with grill-task-planning."]
    header = f"Topic: {topic} · Date: {rc.today()} · Claims: {len(led['claims'])} · Sources: {len(led['sources'])}\n\n"
    title = (directory / "brief.md").read_text(encoding="utf-8").splitlines()[0]
    body_text = re.sub(r"\A# .*\n+", "", markdown)
    rc.write_text(directory / "report.md", f"{title}\n\n{header}{body_text}\n" + "\n".join(appendix))


RUNNERS = {
    "plan": stage_plan, "search": stage_search, "screen": stage_screen, "collect": stage_collect, "analyze": stage_analyze, "critique": stage_critique,
    "judge": stage_judge, "apply": stage_apply, "report": stage_report,
}


def replies_dir(root: Path, topic: str, stage: str) -> Path:
    """Accepted replies of a stage that has not finished yet (ignored run state; see Session.replies)."""
    return root / ".rc-local" / "research" / topic / "replies" / stage


def clear_from(root: Path, topic: str, stage: str, keep_replies: bool = False) -> None:
    """Remove the outputs of stage and every later one, and their kept replies. keep_replies spares the replies
    of stage itself: a stage that stopped half way resumes from the calls it already paid for."""
    directory = topic_dir(root, topic)
    for later in STAGES[STAGES.index(stage):]:
        for name in OUTPUTS[later]:
            path = directory / name
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        if not (keep_replies and later == stage):
            shutil.rmtree(replies_dir(root, topic, later), ignore_errors=True)


def run_research(root: Path, topic: str, start: str | None, budget: int | None) -> int:
    config = rc.settings(root)
    directory = topic_dir(root, topic)
    text = (directory / "brief.md").read_text(encoding="utf-8")
    if brief_status(text) == "retired":
        raise rc.RcError(f"research/{topic} is retired; its report stays as it is")
    if brief_status(text) not in ("accepted", "living", "paused"):
        raise rc.RcError(f"research/{topic}/brief.md is {brief_status(text)}; grill it, then ./rc research accept {topic}")
    ingest.guard(root)
    plan_path = directory / "source-plan.json"
    if not start and plan_path.is_file() and rc.load_json(plan_path).get("briefHash") not in (None, brief_hash(text)):
        # The brief was amended after the plan: every output built on the old brief is stale.
        print(f"research/{topic}/brief.md changed since the plan was made; redoing everything from plan")
        start = "plan"
    if start:
        clear_from(root, topic, start)
    todo = [stage for stage in STAGES if not stage_done(directory, stage)]
    if not todo:
        print(f"research/{topic} is complete; re-run a stage with --from <stage>")
        return 0
    # Later stages read earlier outputs, so a gap means everything after it is redone.
    first = STAGES.index(todo[0])
    clear_from(root, topic, STAGES[first], keep_replies=True)
    import living  # living.py builds on this module, so it is imported where it is used
    living.begin_run(root, topic)
    with rc.Session(root, f"research-{topic}", budget or config["budget"]["researchCalls"]) as session:
        for stage in STAGES[first:]:
            session.say(f"stage {stage} ({STAGES.index(stage) + 1}/{len(STAGES)})")
            session.replies = replies_dir(root, topic, stage)
            RUNNERS[stage](session, root, topic)
            # The committed outputs now hold what the replies said.
            shutil.rmtree(session.replies, ignore_errors=True)
        watch = living.after_run(root, topic)
        if watch:
            session.say(f"living topic, version {watch['version']}: refreshed every {watch['cadenceDays']} days with ./rc research refresh {topic}")
        session.say(f"report ready: research/{topic}/report.md ({session.calls} agent calls); review, then commit research/ and sources/", "gate")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="./rc research")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new")
    new.add_argument("topic")
    new.add_argument("--title", required=True)
    accept = commands.add_parser("accept")
    accept.add_argument("topic")
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("topic")
    run = commands.add_parser("run")
    run.add_argument("topic")
    run.add_argument("--from", dest="start", choices=STAGES)
    run.add_argument("--budget", type=int)
    fresh = commands.add_parser("refresh")
    target = fresh.add_mutually_exclusive_group(required=True)
    target.add_argument("topic", nargs="?")
    target.add_argument("--due", action="store_true", help="refresh every living topic whose cadence has elapsed")
    fresh.add_argument("--budget", type=int)
    for name in ("pause", "resume", "retire"):
        commands.add_parser(name).add_argument("topic")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        import living  # living.py builds on this module, so it is imported where it is used
        if args.command == "refresh":
            if args.due:
                return living.refresh_due(root, args.budget)
            living.refresh(root, args.topic, args.budget)
        elif args.command in ("pause", "resume", "retire"):
            command_status(root, args.topic, args.command)
        elif args.command == "new":
            command_new(root, args)
        elif args.command == "accept":
            command_accept(root, args)
        elif args.command == "list":
            command_list(root, args)
        elif args.command == "show":
            command_show(root, args)
        else:
            return run_research(root, args.topic, args.start, args.budget)
    except (rc.RcError, rc.providers.ProviderError, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
