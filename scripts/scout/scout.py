#!/usr/bin/env python3
"""rc scout [run] [--no-discover] | discover [--since D] [--tag T ...] | cards | dismiss <card>: scouting for a profile.

`rc scout` runs discovery (below), then triage, technology cards and their challenge (cards.py), at about
scout.calls agent calls. `rc scout discover` finds what is new for a profile's interest tags, with no agent.

For every tag the runner asks the adapters for what appeared since the last discovery (plans/active/scouting.md):

github-new     repositories created since then, most starred first          (software pack)
github-active  established repositories (scout.githubMinStars) pushed since  (software pack)
arxiv          the newest arXiv papers matching the tag                       (feed adapter, arXiv API)
openalex       scholarly works published since then                          (openalex)

Results merge by key across tags and sources, so a find surfaced by three tags is one candidate carrying all three.
Anything already in the profile's seen-list is skipped, so a find becomes a candidate once. Repositories get the
profile's licence verdict (scripts/runner/licences.py). A failing source is logged and reported and never stops the
others. Output: scout/candidates/<stamp>.json, scout/runs/<stamp>-searches.json, and scout/seen.json and
scout/state.json updated. The user's GitHub token is lent from gh for the run if GITHUB_TOKEN is unset; it is never
written anywhere.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "runner"), str(HERE.parent / "sources"), str(HERE.parent)]
import cards as carding  # noqa: E402
import kit  # noqa: E402
import licences  # noqa: E402
import rc  # noqa: E402
import sources as registry  # noqa: E402

DEFAULTS = {"lookbackDays": 30, "perQuery": 10, "githubMinStars": 50, "cardsPerRun": 6, "calls": 12, "cadenceDays": 7,
            "sources": ["github-new", "github-active", "arxiv", "openalex"]}
ROLES = ("scoutTriage", "scoutEvaluator", "scoutSceptic")
ARXIV = "http://export.arxiv.org/api/query"
KINDS = {"github": "repository", "feed": "paper", "openalex": "paper", "crossref": "paper", "guardian": "article", "gdelt": "article"}


def settings(root: Path) -> dict[str, Any]:
    return {**DEFAULTS, **rc.settings(root).get("scout", {})}


def profile(root: Path) -> dict[str, Any]:
    path = root / "profile.json"
    if not path.is_file():
        raise rc.RcError("scouting works for a profile; choose one with rc -p <id> (rc profile list shows them)")
    return json.loads(path.read_text(encoding="utf-8"))


def folder(root: Path) -> Path:
    return root / "scout"


def load(path: Path, empty: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else empty


def arxiv_url(tag: str, limit: int) -> str:
    """The arXiv API's newest papers whose title or abstract carries the tag as a phrase."""
    phrase = f'"{tag}"'
    return f"{ARXIV}?" + urllib.parse.urlencode({"search_query": f"ti:{phrase} OR abs:{phrase}", "sortBy": "submittedDate",
                                                 "sortOrder": "descending", "max_results": limit})


def queries(tag: str, since: str, config: dict[str, Any], enabled: set[str]) -> list[tuple[str, str, str, dict[str, str], str | None]]:
    """(source, adapter, query, filters, since) for one tag; a source whose adapter is not enabled is left out."""
    planned = {
        "github-new": ("github", tag, {"created": since, "sort": "stars"}, None),
        "github-active": ("github", tag, {"minStars": str(config["githubMinStars"]), "sort": "stars"}, since),
        "arxiv": ("feed", arxiv_url(tag, config["perQuery"]), {"evidenceType": "preprint"}, since),
        # Quoted: OpenAlex matches loose words otherwise ("TAR stopping rules" found mean-field games).
        "openalex": ("openalex", f'"{tag}"', {}, since),
    }
    return [(source, *planned[source]) for source in config["sources"] if source in planned and planned[source][0] in enabled]


def lend_github_token() -> bool:
    """GITHUB_TOKEN for this process only, from the user's gh login, so search runs at the authenticated rate."""
    if os.environ.get("GITHUB_TOKEN"):
        return True
    gh = shutil.which("gh")
    if not gh:
        return False
    result = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=15)
    token = result.stdout.strip()
    if result.returncode == 0 and token:
        os.environ["GITHUB_TOKEN"] = token
        return True
    return False


def candidate(item: dict[str, Any], tag: str, source: str, kind_of_profile: str, root: Path) -> dict[str, Any]:
    extra = item.get("extra", {})
    found = {"key": item["key"], "title": item["title"], "url": item["url"], "kind": KINDS.get(item["adapter"], "item"),
             "date": item.get("date", ""), "abstract": item.get("abstract", "")[:1200], "authors": item.get("authors", [])[:5],
             "tags": [tag], "sources": [source]}
    if found["kind"] == "repository":
        found.update({"stars": extra.get("stars", 0), "language": extra.get("language"), "topics": extra.get("topics", []),
                      "created": extra.get("created", ""), "archived": extra.get("archived", False),
                      "licence": licences.verdict(root, extra.get("license"), kind_of_profile)})
    if item.get("doi"):
        found["doi"] = item["doi"]
    return found


def stamp_for(directory: Path) -> str:
    base = datetime.date.today().isoformat()
    stamp, number = base, 2
    while (directory / "candidates" / f"{stamp}.json").exists():
        stamp, number = f"{base}-{number}", number + 1
    return stamp


def discover(root: Path, since: str | None = None, only: list[str] | None = None,
             search: Callable[..., list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Run discovery for the profile at root; return the run's summary."""
    search = search or registry.search
    meta = profile(root)
    config = settings(root)
    tags = [item["tag"] for item in meta.get("tags", [])]
    if only:
        wanted = {name.casefold() for name in only}
        tags = [tag for tag in tags if tag.casefold() in wanted]
    if not tags:
        raise rc.RcError("no interest tags to scout for; add some with rc tags add, or rc tags suggest")
    directory = folder(root)
    state = load(directory / "state.json", {})
    since = since or state.get("lastDiscovery") or (datetime.date.today() - datetime.timedelta(days=config["lookbackDays"])).isoformat()
    datetime.date.fromisoformat(since)
    enabled = set(registry.descriptors(root))
    if "github" in enabled and not lend_github_token():
        print("note: no GitHub token (GITHUB_TOKEN or gh login); GitHub search runs at the slower anonymous rate")
    stamp = stamp_for(directory)
    log = directory / "runs" / f"{stamp}-searches.json"
    seen = load(directory / "seen.json", {})
    found: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    total = 0
    skipped = sorted(set(config["sources"]) - {source for tag in tags[:1] for source, *_ in queries(tag, since, config, enabled)})
    for number, tag in enumerate(tags, 1):
        for source, adapter, query, filters, query_since in queries(tag, since, config, enabled):
            try:
                results = search(root, adapter, query, filters, query_since, config["perQuery"], log)
            except (kit.AdapterError, ValueError) as error:  # ValueError: a filter the adapter does not know
                failures.append(f"{source} for '{tag}': {error}")
                continue
            total += len(results)
            for item in results:
                if item["key"] in seen:
                    continue
                kept = found.get(item["key"])
                if kept is None:
                    found[item["key"]] = candidate(item, tag, source, meta.get("type", "company"), root)
                    continue
                kept["tags"] += [tag] if tag not in kept["tags"] else []
                kept["sources"] += [source] if source not in kept["sources"] else []
        print(f"[{number}/{len(tags)}] {tag}: {len(found)} new so far")
    candidates = sorted(found.values(), key=lambda item: (-len(item["tags"]), -item.get("stars", 0), item["title"]))
    today = datetime.date.today().isoformat()
    for item in candidates:
        seen[item["key"]] = {"title": item["title"], "firstSeen": today, "status": "candidate", "run": stamp}
    summary = {"stamp": stamp, "since": since, "tags": tags, "results": total, "new": len(candidates),
               "failures": failures, "sourcesSkipped": skipped}
    rc.write_json(directory / "candidates" / f"{stamp}.json", {**summary, "candidates": candidates})
    rc.write_json(directory / "seen.json", seen)
    rc.write_json(directory / "state.json", {**state, "lastDiscovery": today})
    return summary


def report_discovery(summary: dict[str, Any]) -> None:
    print(f"{summary['new']} new candidates from {summary['results']} results since {summary['since']}: "
          f"scout/candidates/{summary['stamp']}.json")
    for line in summary["failures"]:
        print(f"warning: {line}")
    if summary["sourcesSkipped"]:
        print(f"note: not searched, adapter not enabled: {', '.join(summary['sourcesSkipped'])} (rc sources packs)")


TREND_TAGS = ("AI coding agent", "agent harness", "open-weight LLM", "local LLM inference", "LLM evaluation",
              "RAG framework", "developer tooling")


def command_init_trends(root: Path) -> None:
    """Start the instance's shared trend feed: trends/ scouted like a profile, every card judged against all
    profiles. Starts with general tags the user edits with rc trends tags."""
    if root.name != carding.TRENDS or not (root.parent / "research-center.json").is_file():
        raise rc.RcError("the trend feed lives in an instance's trends/ folder; run rc trends init")
    if (root / "profile.json").is_file():
        raise rc.RcError("the trend feed already exists; edit its tags with rc trends tags")
    today = datetime.date.today().isoformat()
    rc.write_json(root / "profile.json", {
        "schemaVersion": 1, "id": carding.TRENDS, "name": "Trends across profiles", "type": "company", "createdAt": today,
        "description": "Releases and research that may change how any profile works or builds its software, judged against "
                       "every profile, under the strictest licence rule.",
        "tags": [{"tag": tag, "why": "a default trend tag", "source": "user", "evidence": [], "added": today} for tag in TREND_TAGS]})
    print(f"started trends/ with the tags {', '.join(TREND_TAGS)}; edit them with rc trends tags, then rc trends")


def all_cards(root: Path) -> list[dict[str, Any]]:
    return sorted((json.loads(path.read_text(encoding="utf-8")) for path in (folder(root) / "cards").glob("*.json")),
                  key=lambda card: (card["date"], card["id"]), reverse=True)


def command_run(root: Path, find: bool = True) -> dict[str, Any]:
    profile(root)
    config = settings(root)
    pipeline = rc.settings(root)["pipeline"]
    missing = [role for role in ROLES if role not in pipeline]
    if missing:
        raise rc.RcError(f"pipeline has no {', '.join(missing)}; run rc upgrade from the template")
    stamp = datetime.date.today().isoformat()
    if find:
        summary = discover(root)
        report_discovery(summary)
        stamp = summary["stamp"]
    result = carding.run(root, config, {role: pipeline[role] for role in ROLES}, stamp)
    state_path = folder(root) / "state.json"
    rc.write_json(state_path, {**load(state_path, {}), "lastRun": datetime.date.today().isoformat()})
    if not result["triaged"]:
        print("no open candidates to triage; run discovery first (rc scout discover)")
        return result
    print(f"triaged {result['triaged']} candidates; {len(result['cards'])} cards in {result.get('calls', 0)} agent calls:")
    for card in all_cards(root):
        if card["id"] in result["cards"]:
            print(f"  [{card['verdict']}] {card['title']}: {card['headline']}  (scout/cards/{card['id']}.md)")
    for line in result["failures"]:
        print(f"warning: no card for {line}")
    return result


def is_due(root: Path, today: datetime.date | None = None) -> bool:
    """A profile is due when it has tags and its last full scout is scout.cadenceDays or more ago (or never ran)."""
    meta = profile(root)
    if not meta.get("tags"):
        return False
    last = load(folder(root) / "state.json", {}).get("lastRun")
    if not last:
        return True
    today = today or datetime.date.today()
    return (today - datetime.date.fromisoformat(last)).days >= settings(root)["cadenceDays"]


def command_due(root: Path) -> dict[str, Any] | None:
    if not is_due(root):
        print(f"{profile(root).get('name', root.name)}: not due")
        return None
    return command_run(root)


def slug_topic(text: str) -> str:
    return carding.slug(text)[:48].strip("-") or "card"


def command_dive(root: Path, identifier: str, topic: str | None = None) -> Path:
    """Turn a card into a draft research brief - the deep dive - pre-filled from the card: its component, what it
    does today, the claims to test, the constraints, and the card's pass bar as the success criterion. The user
    grills and accepts it (grill-research-topic); nothing runs until then."""
    path = folder(root) / "cards" / f"{identifier}.json"
    if not path.is_file():
        raise rc.RcError(f"no card {identifier}; rc scout cards lists them")
    if carding.is_trends(root):
        raise rc.RcError("a trend card belongs to every profile; dive into it from the profile it affects (rc -p <id> research new)")
    card = json.loads(path.read_text(encoding="utf-8"))
    meta = profile(root)
    engineers, plan = card["engineers"], card["engineers"]["evaluation"]
    topic = topic or slug_topic(card["title"].split("/")[-1])
    directory = root / "research" / topic
    if directory.exists():
        raise rc.RcError(f"topic {topic} already exists; pass another id")
    licence = card.get("licence")
    licence_line = (f" Its licence ({licence['spdx'] or 'none found'}, {licence['class']}) is "
                    + ("usable by this profile." if licence["usable"] else f"not usable by this {meta.get('type')} profile: {licence['reason']}.")
                    if licence else "")
    sections = {
        "Topic": (f"Whether {card['title']} ({card['url']}) should change {engineers['component']}. The scout's card ({card['date']}, "
                  f"verdict: {card['verdict']}) says: {card['headline']} This study tests that verdict with cited evidence before "
                  "anyone builds on it."),
        "Questions": "\n".join([
            # What the component does today stays in Our needs: pasted into a question it makes the question unreadable.
            f"- Q1: Does {card['title']} do better than what {engineers['component']} does today, measured as "
            f"{plan['metric'].rstrip('.')}, on data like ours?",
            f"- Q2: Which constraints does it meet or break for us: licence, data residency, language, scale and maintenance?{licence_line}",
            f"- Q3: What would integrating it take: what it replaces ({engineers['replaces']}), the effort and the risks?",
            "- Q4: How does it compare with the alternatives named under Our needs?"]),
        "Scope": f"{card['title']}, its documented results and independent evaluations, and the alternatives the card names. Recent work first.",
        "Out of scope": "Other uses of the technology that do not bear on the component above.",
        "Our needs": (f"The component: {engineers['component']}. Today: {engineers['componentToday']} Alternatives: "
                      f"{engineers['alternatives']} The card's evidence rests on "
                      f"{card['evidence']}; the fit on {', '.join(card.get('profileBasis', []))}."),
        "Success criteria": (f"A decision on the card's verdict. The card's evaluation plan is the bar: {plan['experiment']}; "
                             f"metric {plan['metric']}; pass bar {plan['passBar']}; effort {plan['effort']}."),
        "Source preferences": "The project's own documentation and code, peer-reviewed or reproduced evaluations, issue trackers for known "
                              "problems; distrust vendor benchmarks without method.",
        "Living": "Cadence: none\nRetire when: the verdict is decided.",
    }
    template = (rc.instance(root) / "templates" / "brief.md").read_text(encoding="utf-8")
    head = template.split("\n## ", 1)[0].replace("<topic-id>", topic).replace("<title>", f"Should {card['title']} change {engineers['component']}?")
    text = head + "".join(f"\n## {name}\n\n{body}\n" for name, body in sections.items())
    text += "\n## Amendments\n\nNone. Log here every change made to the questions, scope or needs after acceptance, with its date; a changed brief redoes the research from plan.\n"
    rc.write_text(directory / "brief.md", text)
    card["status"] = "deep dive"
    card["research"] = topic
    carding.write_card(root, card)
    print(f"drafted research/{topic}/brief.md from the card; review it with the grill-research-topic skill, then "
          f"rc research accept {topic}")
    return directory / "brief.md"


def command_cards(root: Path) -> None:
    cards = all_cards(root)
    if not cards:
        print("no cards yet: rc scout")
    for card in cards:
        status = "" if card.get("status", "open") == "open" else f" ({card['status']})"
        print(f"{card['date']}  [{card['verdict']}]{status} {card['title']}  scout/cards/{card['id']}.md")


def command_dismiss(root: Path, identifier: str) -> None:
    """Close a card for good: its find is never raised again."""
    path = folder(root) / "cards" / f"{identifier}.json"
    if not path.is_file():
        raise rc.RcError(f"no card {identifier}; rc scout cards lists them")
    card = json.loads(path.read_text(encoding="utf-8"))
    card["status"] = "dismissed"
    carding.write_card(root, card)
    carding.mark(root, [card["key"]], "dismissed", card["stamp"])
    print(f"dismissed {card['title']}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="rc scout")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command")
    run_parser = commands.add_parser("run", help="discovery, triage, cards and their challenge (the default)")
    run_parser.add_argument("--no-discover", action="store_true", help="only triage the open candidates")
    find = commands.add_parser("discover", help="find what is new for the profile's tags, with no agent")
    find.add_argument("--since", help="YYYY-MM-DD; default: the last discovery, else scout.lookbackDays ago")
    find.add_argument("--tag", action="append", help="only this tag; repeatable")
    commands.add_parser("cards", help="the profile's technology cards, newest first")
    commands.add_parser("init", help="start the instance's shared trend feed (rc trends init)")
    commands.add_parser("due", help="a full scout if scout.cadenceDays have passed since the last one")
    dive = commands.add_parser("dive", help="turn a card into a draft research brief")
    dive.add_argument("card")
    dive.add_argument("--topic", help="the research topic id (default: from the card's title)")
    commands.add_parser("dismiss", help="close a card; its find is never raised again").add_argument("card")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "discover":
            report_discovery(discover(root, args.since, args.tag))
        elif args.command == "cards":
            command_cards(root)
        elif args.command == "init":
            command_init_trends(root)
        elif args.command == "due":
            command_due(root)
        elif args.command == "dive":
            command_dive(root, args.card, args.topic)
        elif args.command == "dismiss":
            command_dismiss(root, args.card)
        else:
            command_run(root, not getattr(args, "no_discover", False))
    except (rc.RcError, rc.providers.ProviderError, OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
