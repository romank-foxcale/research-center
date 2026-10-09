#!/usr/bin/env python3
"""./rc research: a topic's brief, then a fixed, resumable pipeline that ends in a cited report.

plan     source-planner reads the brief and profile          -> source-plan.json
collect  researchers search the web in parallel; the runner  -> claims.json (+ sources/web-<topic>/)
         stores every cited page and checks every quote
analyze  analyst answers the questions from the ledger       -> analysis.md, ideas.json
critique sceptics try to disprove each claim, in parallel    -> critique/review-<x>.json
judge    the judge reads the reviews as anonymous labels     -> judgement.json
apply    applier fits surviving ideas to the user's repos    -> fit.json, fit.md, handoff.md
report   reporter writes the answer; the runner checks it    -> report.md

Each stage's output is committed under research/<topic>/; a run resumes at the first missing output.
See docs/decisions/0004-research-pipeline.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
import extract  # noqa: E402
import ingest  # noqa: E402
import rc  # noqa: E402

STAGES = ("plan", "collect", "analyze", "critique", "judge", "apply", "report")
OUTPUTS = {
    "plan": ["source-plan.json", "source-plan.md"],
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
SECTIONS = ("Topic", "Questions", "Scope", "Out of scope", "Our needs", "Success criteria", "Source preferences")
QUESTION = re.compile(r"^- (Q\d+):\s*(\S.*)$", re.MULTILINE)
CLAIM_REF = re.compile(r"\[(C\d+)\]")
IDEA_ID = re.compile(r"I\d+")
SOURCE_KINDS = ("paper", "docs", "blog", "repo", "news", "forum", "talk", "other")


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
    return problems


def brief_status(text: str) -> str:
    match = re.search(r"^Status:\s*(\S+)", text, flags=re.MULTILINE)
    return match.group(1) if match else "unknown"


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
    path.write_text(re.sub(r"^Status:\s*\S+", "Status: accepted", text, count=1, flags=re.MULTILINE), encoding="utf-8", newline="\n")
    print(f"accepted research/{args.topic}/brief.md; run it with ./rc research run {args.topic}")


def stage_done(directory: Path, stage: str) -> bool:
    if stage == "critique":
        return any((directory / "critique").glob("review-*.json"))
    if stage == "apply":
        return (directory / "fit.json").is_file()
    return all((directory / name).exists() for name in OUTPUTS[stage])


def command_list(root: Path, _: argparse.Namespace) -> None:
    for brief in sorted((root / "research").glob("*/brief.md")):
        directory = brief.parent
        done = [stage for stage in STAGES if stage_done(directory, stage)]
        title = brief.read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
        print(f"{directory.name:<32} {brief_status(brief.read_text(encoding='utf-8')):<9} {len(done)}/{len(STAGES)} stages  {title}")


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


def stage_plan(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)

    def check(data: Any) -> dict[str, Any]:
        avenues = data.get("avenues") if isinstance(data, dict) else None
        if not avenues:
            raise ValueError("expected {\"avenues\": [{\"where\", \"queries\", \"why\", \"questions\"}]}")
        known = set(questions(root, topic))
        for avenue in avenues:
            if not avenue.get("where") or not avenue.get("why") or not avenue.get("queries"):
                raise ValueError(f"avenue {avenue} needs where, why and queries")
            unknown = set(avenue.get("questions", [])) - known
            if unknown:
                raise ValueError(f"avenue {avenue.get('where')} refers to unknown questions {sorted(unknown)}")
        return data

    body = f"# Task\n\nPlan where to search.\n\n{context(root, topic)}"
    data = session.call_checked(config["pipeline"]["sourcePlanner"], body, "plan", json_reply(check))
    directory = topic_dir(root, topic)
    rc.write_json(directory / "source-plan.json", data)
    lines = [f"# Source plan: {topic}\n"]
    for avenue in data["avenues"]:
        lines.append(f"## {avenue['where']}\n\nWhy: {avenue['why']}\n\nQuestions: {', '.join(avenue.get('questions', []))}\n")
        lines += [f"- `{query}`" for query in avenue["queries"]]
        lines.append("")
    rc.write_text(directory / "source-plan.md", "\n".join(lines))


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
    """True when the quote is in the stored page: whole, or 80% of its five-word runs (conversion reflows text)."""
    needle, haystack = normalized(quote), normalized(text)
    if not needle:
        return False
    if needle in haystack:
        return True
    words = needle.split()
    runs = [" ".join(words[index:index + 5]) for index in range(max(1, len(words) - 4))]
    return len(words) >= 5 and sum(run in haystack for run in runs) >= 0.8 * len(runs)


def canonical_url(url: str) -> str:
    return re.sub(r"[#?].*$", "", url.strip()).rstrip("/").lower().replace("http://", "https://").replace("://www.", "://")


def stage_collect(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    known = set(questions(root, topic))
    limit = config["research"]["maxSourcesPerResearcher"]

    def check(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict) or not data.get("sources") or not data.get("claims"):
            raise ValueError("expected {\"sources\": [...], \"claims\": [...]} with at least one of each")
        refs = {source.get("ref") for source in data["sources"]}
        for source in data["sources"]:
            if not str(source.get("url", "")).startswith(("http://", "https://")):
                raise ValueError(f"source {source.get('ref')} needs an http(s) url")
        for claim in data["claims"]:
            if claim.get("source") not in refs:
                raise ValueError(f"claim {claim.get('text', '')[:60]!r} cites unknown source {claim.get('source')}")
            if not claim.get("text") or not claim.get("quote"):
                raise ValueError(f"claim {claim.get('text', '')[:60]!r} needs text and a verbatim quote")
            if set(claim.get("questions", [])) - known:
                raise ValueError(f"claim {claim.get('text', '')[:60]!r} refers to unknown questions")
        data["sources"] = data["sources"][:limit]
        return data

    body = (
        f"# Task\n\nCollect evidence following research/{topic}/source-plan.md. At most {limit} sources.\n\n{context(root, topic)}"
    )
    researchers = config["pipeline"]["researchers"]
    replies = session.parallel([
        (role_id, lambda role_id=role_id: session.call_checked(role_id, body, f"collect-{role_id}", json_reply(check)))
        for role_id in researchers
    ])

    # Merge sources across researchers by URL, then store each page so every claim has committed evidence.
    merged: dict[str, dict[str, Any]] = {}
    claims: list[dict[str, Any]] = []
    for role_id in researchers:
        reply = replies[role_id]
        local = {}
        for source in reply["sources"]:
            key = canonical_url(source["url"])
            entry = merged.setdefault(key, {
                "id": f"S{len(merged) + 1}", "url": source["url"], "title": source.get("title", ""),
                "published": source.get("published", "unknown"),
                "kind": source.get("kind") if source.get("kind") in SOURCE_KINDS else "other", "foundBy": [],
            })
            entry["foundBy"] = sorted(set(entry["foundBy"]) | {role_id})
            local[source["ref"]] = entry["id"]
        for claim in reply["claims"]:
            claims.append({
                "text": " ".join(claim["text"].split()), "source": local[claim["source"]], "quote": " ".join(claim["quote"].split()),
                "questions": claim.get("questions", []), "type": claim.get("type", "fact"), "foundBy": role_id,
            })

    source_id = f"web-{topic}"[:60].strip("-")
    entries, texts, skipped = {}, {}, []
    for entry in merged.values():
        try:
            stored, text, extractor, data = ingest.url_document(entry["url"])
        except (extract.Skip, urllib.error.URLError, OSError, ValueError) as reason:
            entry["fetch"] = f"failed: {str(reason)[:160]}"
            entry["stored"] = None
            skipped.append({"origin": entry["url"], "reason": entry["fetch"]})
            continue
        texts[stored] = text
        entries[stored] = {"origin": entry["url"], "sha256": hashlib.sha256(data).hexdigest(), "extractor": extractor}
        entry["fetch"] = "ok"
        entry["stored"] = f"sources/{source_id}/text/{stored}"
    descriptor = {
        "schemaVersion": 1, "id": source_id, "kind": "url", "locators": [entry["url"] for entry in merged.values()],
        "include": [], "exclude": [], "depth": 0, "maxDocuments": len(merged), "note": f"pages cited by research/{topic}",
        "origin": f"research:{topic}", "addedAt": rc.today(),
    }
    rc.write_json(ingest.source_path(root, source_id), descriptor)
    ingest.store(root, descriptor, entries, texts, skipped, {})

    sources_by_id = {entry["id"]: entry for entry in merged.values()}
    for number, claim in enumerate(claims, 1):
        claim["id"] = f"C{number}"
        stored = sources_by_id[claim["source"]].get("stored")
        claim["quoteVerified"] = bool(stored) and quote_found(claim["quote"], (root / stored).read_text(encoding="utf-8"))
    ledger = {"topic": topic, "sources": list(merged.values()), "claims": [{"id": claim.pop("id"), **claim} for claim in claims]}
    directory = topic_dir(root, topic)
    rc.write_json(directory / "claims.json", ledger)
    rc.write_text(directory / "claims.md", render_ledger(ledger))
    fetched = sum(entry["fetch"] == "ok" for entry in merged.values())
    verified = sum(claim["quoteVerified"] for claim in ledger["claims"])
    session.say(f"collect: {len(ledger['claims'])} claims from {len(merged)} sources ({fetched} stored); {verified} quotes verified")


def render_ledger(ledger: dict[str, Any]) -> str:
    sources = {source["id"]: source for source in ledger["sources"]}
    lines = [f"# Claims ledger: {ledger['topic']}\n", "A claim whose quote is not verified, or whose page could not be stored, "
             "rests on the researcher's word alone.\n", "| Claim | Text | Source | Quote verified | Questions |", "| --- | --- | --- | --- | --- |"]
    for claim in ledger["claims"]:
        source = sources[claim["source"]]
        where = source.get("stored") or f"{source['url']} (not stored)"
        lines.append(f"| {claim['id']} | {cell(claim['text'])} | {source['id']}: {cell(where)} | {'yes' if claim['quoteVerified'] else 'no'} | {', '.join(claim['questions'])} |")
    lines += ["", "## Sources", ""]
    lines += [f"- {source['id']}: [{source.get('title') or source['url']}]({source['url']}) ({source['kind']}, published {source['published']}) "
              f"stored: {source.get('stored') or source.get('fetch')}" for source in ledger["sources"]]
    return "\n".join(lines)


def ledger(root: Path, topic: str) -> dict[str, Any]:
    return rc.load_json(topic_dir(root, topic) / "claims.json")


def stage_analyze(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    claim_ids = {claim["id"] for claim in ledger(root, topic)["claims"]}
    known = set(questions(root, topic))

    def check(reply: str) -> tuple[str, dict[str, Any]]:
        ideas = rc.extract_json(reply)
        if not isinstance(ideas, dict) or not ideas.get("ideas"):
            raise ValueError("end with a ```json block {\"ideas\": [{\"id\": \"I1\", \"name\", \"summary\", \"claims\": [...]}]}")
        markdown = re.sub(r"```json\s*\n.*?\n```\s*\Z", "", reply.strip(), flags=re.DOTALL).strip()
        unknown = set(CLAIM_REF.findall(markdown)) - claim_ids
        for idea in ideas["ideas"]:
            if not IDEA_ID.fullmatch(str(idea.get("id", ""))) or not idea.get("name"):
                raise ValueError(f"idea {idea} needs an id like I1 and a name")
            unknown |= set(idea.get("claims", [])) - claim_ids
        if unknown:
            raise ValueError(f"cites claims that are not in the ledger: {sorted(unknown)}")
        missing = [question for question in sorted(known) if question not in markdown]
        if missing:
            raise ValueError(f"does not answer {missing}: give each question its own section")
        return markdown, ideas

    body = f"# Task\n\nAnswer the brief's questions from research/{topic}/claims.md.\n\n{context(root, topic)}"
    markdown, ideas = session.call_checked(config["pipeline"]["analyst"], body, "analyze", check)
    directory = topic_dir(root, topic)
    rc.write_text(directory / "analysis.md", markdown)
    rc.write_json(directory / "ideas.json", ideas)


def cited_claims(root: Path, topic: str) -> list[str]:
    directory = topic_dir(root, topic)
    cited = set(CLAIM_REF.findall((directory / "analysis.md").read_text(encoding="utf-8")))
    for idea in rc.load_json(directory / "ideas.json")["ideas"]:
        cited |= set(idea.get("claims", []))
    return sorted(cited, key=lambda value: int(value[1:]))


def stage_critique(session: rc.Session, root: Path, topic: str) -> None:
    config = rc.settings(root)
    wanted = cited_claims(root, topic)

    def check(data: Any) -> dict[str, Any]:
        verdicts = data.get("claims") if isinstance(data, dict) else None
        if not isinstance(verdicts, list):
            raise ValueError("expected {\"claims\": [{\"claim\", \"verdict\", \"reason\", \"evidence\"}], \"analysis\": [...]}")
        seen = {item.get("claim") for item in verdicts}
        missing = sorted(set(wanted) - seen, key=lambda value: int(value[1:]))
        bad = [item for item in verdicts if item.get("verdict") not in CLAIM_VERDICTS or not item.get("reason")]
        if missing or bad:
            raise ValueError(f"missing verdicts for {missing}; invalid entries {bad[:3]} (verdict one of {CLAIM_VERDICTS} with a reason)")
        return data

    body = (
        f"# Task\n\nTry to disprove the claims that research/{topic}/analysis.md and ideas.json rely on: {', '.join(wanted)}. "
        f"The ledger is research/{topic}/claims.md; stored pages are under sources/.\n\n{context(root, topic)}"
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

    def check(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("expected {\"claims\": [...], \"ideas\": [...]}")
        claim_seen = {item.get("claim"): item for item in data.get("claims", [])}
        idea_seen = {item.get("idea"): item for item in data.get("ideas", [])}
        problems = [f"no verdict for {claim}" for claim in wanted if claim not in claim_seen]
        problems += [f"no verdict for idea {idea}" for idea in ideas if idea not in idea_seen]
        problems += [f"{key}: verdict must be one of {CLAIM_VERDICTS}" for key, item in claim_seen.items() if item.get("verdict") not in CLAIM_VERDICTS]
        problems += [f"{key}: verdict must be one of {IDEA_VERDICTS}" for key, item in idea_seen.items() if item.get("verdict") not in IDEA_VERDICTS]
        if problems:
            raise ValueError("; ".join(problems[:20]))
        return data

    shown = "\n\n".join(f"## Review {label}\n\n```json\n{json.dumps(review, ensure_ascii=False, indent=1)[:60000]}\n```"
                        for label, review in reviews.items())
    body = (
        f"# Task\n\nSettle every claim ({', '.join(wanted)}) and idea ({', '.join(ideas)}) of research/{topic}/analysis.md "
        f"and ideas.json from these anonymous reviews, checking them against the stored sources.\n\n{context(root, topic)}\n\n{shown}"
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
    rc.write_json(directory / "judgement.json", data)
    lines = [f"# Judgement: {topic}\n", "| Claim | Verdict | Reason |", "| --- | --- | --- |"]
    lines += [f"| {item['claim']} | {item['verdict']} | {cell(item.get('reason', ''))} |" for item in data["claims"]]
    lines += ["", "| Idea | Verdict | Reason |", "| --- | --- | --- |"]
    lines += [f"| {item['idea']} | {item['verdict']} | {cell(item.get('reason', ''))} |" for item in data["ideas"]]
    if contested:
        lines += ["", "## Contested", ""] + [f"- {item['claim']}: refuted by {', '.join(item['refutedBy'])}, kept by the judge" for item in contested]
    rc.write_text(directory / "judgement.md", "\n".join(lines))


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
            problems += [f"{fit.get('idea')}: cites unknown claim {claim}" for claim in set(CLAIM_REF.findall(text)) - claim_ids]
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
        cited = set(CLAIM_REF.findall(markdown))
        problems = [f"cites {claim}, which is not in the ledger" for claim in sorted(cited) if claim not in {c["id"] for c in led["claims"]}]
        problems += [f"relies on {claim}, judged {verdicts[claim]}: drop it or name it as refuted outside a [C#] citation"
                     for claim in sorted(cited) if verdicts.get(claim) in ("REFUTED", "UNSUPPORTED")]
        problems += [f"does not answer {question}" for question in known if question not in markdown]
        if not cited:
            problems.append("cites no claim: every finding needs a [C#] citation")
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
    used = sorted(set(CLAIM_REF.findall(markdown)), key=lambda value: int(value[1:]))
    appendix = ["", "## Evidence", "", "| Claim | Verdict | Quote verified | Source |", "| --- | --- | --- | --- |"]
    for claim_id in used:
        claim, source = claims[claim_id], sources[claims[claim_id]["source"]]
        appendix.append(f"| {claim_id} | {verdicts.get(claim_id, 'not judged')} | {'yes' if claim['quoteVerified'] else 'no'} | "
                        f"[{cell(source.get('title') or source['url'])}]({source['url']}){' — ' + source['stored'] if source.get('stored') else ''} |")
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
    "plan": stage_plan, "collect": stage_collect, "analyze": stage_analyze, "critique": stage_critique,
    "judge": stage_judge, "apply": stage_apply, "report": stage_report,
}


def clear_from(root: Path, topic: str, stage: str) -> None:
    directory = topic_dir(root, topic)
    for later in STAGES[STAGES.index(stage):]:
        for name in OUTPUTS[later]:
            path = directory / name
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)


def run_research(root: Path, topic: str, start: str | None, budget: int | None) -> int:
    config = rc.settings(root)
    directory = topic_dir(root, topic)
    text = (directory / "brief.md").read_text(encoding="utf-8")
    if brief_status(text) != "accepted":
        raise rc.RcError(f"research/{topic}/brief.md is {brief_status(text)}; grill it, then ./rc research accept {topic}")
    ingest.guard(root)
    if start:
        clear_from(root, topic, start)
    todo = [stage for stage in STAGES if not stage_done(directory, stage)]
    if not todo:
        print(f"research/{topic} is complete; re-run a stage with --from <stage>")
        return 0
    # Later stages read earlier outputs, so a gap means everything after it is redone.
    first = STAGES.index(todo[0])
    clear_from(root, topic, STAGES[first])
    with rc.Session(root, f"research-{topic}", budget or config["budget"]["researchCalls"]) as session:
        for stage in STAGES[first:]:
            session.say(f"stage {stage} ({STAGES.index(stage) + 1}/{len(STAGES)})")
            RUNNERS[stage](session, root, topic)
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
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "new":
            command_new(root, args)
        elif args.command == "accept":
            command_accept(root, args)
        elif args.command == "list":
            command_list(root, args)
        elif args.command == "show":
            command_show(root, args)
        else:
            return run_research(root, args.topic, args.start, args.budget)
    except (rc.RcError, OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
