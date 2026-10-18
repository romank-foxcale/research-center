#!/usr/bin/env python3
"""rc scout discover [--since D] [--tag T ...]: find what is new for a profile's interest tags, with no agent.

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
import kit  # noqa: E402
import licences  # noqa: E402
import rc  # noqa: E402
import sources as registry  # noqa: E402

DEFAULTS = {"lookbackDays": 30, "perQuery": 10, "githubMinStars": 50,
            "sources": ["github-new", "github-active", "arxiv", "openalex"]}
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
        "openalex": ("openalex", tag, {}, since),
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="rc scout")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("discover", help="find what is new for the profile's tags, with no agent")
    find.add_argument("--since", help="YYYY-MM-DD; default: the last discovery, else scout.lookbackDays ago")
    find.add_argument("--tag", action="append", help="only this tag; repeatable")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        summary = discover(root, args.since, args.tag)
    except (rc.RcError, OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"{summary['new']} new candidates from {summary['results']} results since {summary['since']}: "
          f"scout/candidates/{summary['stamp']}.json")
    for line in summary["failures"]:
        print(f"warning: {line}")
    if summary["sourcesSkipped"]:
        print(f"note: not searched, adapter not enabled: {', '.join(summary['sourcesSkipped'])} (rc sources packs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
