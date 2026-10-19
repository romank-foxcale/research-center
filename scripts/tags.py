#!/usr/bin/env python3
"""rc tags list | add <tag> [--why] | remove <tag> | rename <old> <new> | suggest | accept [<tag>...|--all]
| reject [<tag>...|--all]: a profile's interest tags, what the scout searches for (docs/decisions/0015-profiles.md).

Tags live in the profile's profile.json. The user writes them, or the tagger role proposes them from the profile's
description, scope, profile notes and digests - each with a reason and the files it rests on. Proposals wait in
suggestedTags until the user accepts or rejects them; a rejected tag is never proposed again.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "runner"))
import rc  # noqa: E402

MAX_WORDS = 5
MAX_SUGGESTIONS = 15
SUGGEST_BUDGET = 2  # one call and its retry
EVIDENCE_ROOTS = ("profile.json", "scope.md", "knowledge/", "sources/", "inbox/")


def meta_path(root: Path) -> Path:
    path = root / "profile.json"
    if not path.is_file():
        raise rc.RcError("tags belong to a profile; choose one with rc -p <id> (rc profile list shows them)")
    return path


def load(root: Path) -> dict[str, Any]:
    return json.loads(meta_path(root).read_text(encoding="utf-8"))


def save(root: Path, meta: dict[str, Any]) -> None:
    rc.write_json(meta_path(root), meta)


def clean(tag: str) -> str:
    text = " ".join(str(tag).split()).strip(" ,;#")
    if not text:
        raise rc.RcError("a tag needs some text")
    if len(text.split()) > MAX_WORDS:
        raise rc.RcError(f"keep a tag to {MAX_WORDS} words or fewer, so the scout can search for it: {text}")
    return text


def key(tag: str) -> str:
    return clean(tag).casefold()


def names(items: list[dict[str, Any]]) -> list[str]:
    return [item["tag"] for item in items]


def find(items: list[dict[str, Any]], tag: str) -> dict[str, Any] | None:
    return next((item for item in items if key(item["tag"]) == key(tag)), None)


def command_add(root: Path, tag: str, why: str = "") -> None:
    meta = load(root)
    tags, pending = meta.setdefault("tags", []), meta.setdefault("suggestedTags", [])
    if find(tags, tag):
        raise rc.RcError(f"already a tag: {clean(tag)}")
    proposal = find(pending, tag)
    if proposal:
        pending.remove(proposal)
    tags.append(
        {
            "tag": clean(tag),
            "why": " ".join(why.split()) or (proposal or {}).get("why", ""),
            "source": "user",
            "evidence": (proposal or {}).get("evidence", []),
            "added": rc.today(),
        }
    )
    meta["rejectedTags"] = [name for name in meta.get("rejectedTags", []) if name.casefold() != key(tag)]
    save(root, meta)
    print(f"added tag: {clean(tag)}")


def command_remove(root: Path, tag: str) -> None:
    meta = load(root)
    item = find(meta.get("tags", []), tag)
    if not item:
        raise rc.RcError(f"no tag {clean(tag)}; rc tags list shows them")
    meta["tags"].remove(item)
    save(root, meta)
    print(f"removed tag: {item['tag']}")


def command_rename(root: Path, old: str, new: str) -> None:
    meta = load(root)
    item = find(meta.get("tags", []), old)
    if not item:
        raise rc.RcError(f"no tag {clean(old)}; rc tags list shows them")
    if key(old) != key(new) and find(meta["tags"], new):
        raise rc.RcError(f"already a tag: {clean(new)}")
    item["tag"] = clean(new)
    save(root, meta)
    print(f"renamed tag: {clean(old)} -> {clean(new)}")


def suggestion_problems(data: Any, root: Path, taken: set[str]) -> list[str]:
    """A proposal names a short, searchable tag that is not already taken or rejected, says why, and rests on files
    of the profile that exist."""
    if not isinstance(data, dict) or not isinstance(data.get("tags"), list) or not data["tags"]:
        return ["reply with a JSON object whose tags is a non-empty list"]
    problems = []
    if len(data["tags"]) > MAX_SUGGESTIONS:
        problems.append(f"propose at most {MAX_SUGGESTIONS} tags")
    seen: set[str] = set()
    for index, item in enumerate(data["tags"], 1):
        if not isinstance(item, dict):
            problems.append(f"tag {index} must be an object with tag, why and evidence")
            continue
        text = " ".join(str(item.get("tag", "")).split())
        label = text or f"tag {index}"
        if not text:
            problems.append(f"tag {index} has no text")
        elif len(text.split()) > MAX_WORDS:
            problems.append(f"'{label}' has more than {MAX_WORDS} words")
        elif text.casefold() in taken:
            problems.append(f"'{label}' is already a tag or was rejected; leave it out")
        elif text.casefold() in seen:
            problems.append(f"'{label}' is proposed twice")
        seen.add(text.casefold())
        if not str(item.get("why", "")).strip():
            problems.append(f"'{label}' needs a why")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            problems.append(f"'{label}' needs evidence: the profile files it rests on")
            continue
        for path in evidence:
            relative = re.sub(r"#.*$", "", str(path)).replace("\\", "/")
            if not relative.startswith(EVIDENCE_ROOTS) or not (root / relative).is_file():
                problems.append(f"'{label}' cites {path}, which is not a file of this profile")
    return problems


def command_suggest(root: Path) -> list[dict[str, Any]]:
    meta = load(root)
    config = rc.settings(root)
    taken = {name.casefold() for name in names(meta.get("tags", []))} | {
        name.casefold() for name in meta.get("rejectedTags", [])
    }
    read = ["profile.json"] + (["scope.md"] if (root / "scope.md").is_file() else [])
    if (root / "knowledge" / "profile" / "index.md").is_file():
        read.append("knowledge/profile/index.md and the notes it links")
    if any((root / "knowledge" / "digests").glob("*.md")):
        read.append("knowledge/digests/")
    if len(read) == 1 and not meta.get("description"):
        raise rc.RcError(
            "nothing to propose tags from: describe the profile (rc profile edit --description) or ingest its material first"
        )
    body = (
        f"# Task\n\nPropose interest tags for the profile {meta.get('name', root.name)} ({meta.get('type')}). "
        f"Read {', '.join(read)}.\n\n"
        f"Current tags: {', '.join(names(meta.get('tags', []))) or 'none'}.\n"
        f"Rejected before, never propose again: {', '.join(meta.get('rejectedTags', [])) or 'none'}.\n"
    )

    def check(reply: str) -> list[dict[str, Any]]:
        data = rc.extract_json(reply)
        problems = suggestion_problems(data, root, taken)
        if problems:
            raise ValueError("; ".join(problems[:15]))
        return [
            {
                "tag": " ".join(str(item["tag"]).split()),
                "why": " ".join(str(item["why"]).split()),
                "source": "agent",
                "evidence": [str(path) for path in item["evidence"]],
            }
            for item in data["tags"]
        ]

    with rc.Session(root, "tags", SUGGEST_BUDGET) as session:
        proposals = session.call_checked(config["pipeline"]["tagger"], body, "tags", check)
    meta = load(root)
    meta["suggestedTags"] = proposals
    save(root, meta)
    print(f"{len(proposals)} tags proposed; accept with rc tags accept <tag>... (or --all), reject with rc tags reject")
    for item in proposals:
        print(f"  {item['tag']}: {item['why']}")
    return proposals


def chosen(pending: list[dict[str, Any]], wanted: list[str], every: bool) -> list[dict[str, Any]]:
    if every:
        return list(pending)
    picked = []
    for tag in wanted:
        item = find(pending, tag)
        if not item:
            raise rc.RcError(f"no proposed tag {clean(tag)}; rc tags list shows the proposals")
        picked.append(item)
    if not picked:
        raise rc.RcError("name the proposed tags, or pass --all")
    return picked


def command_accept(root: Path, wanted: list[str], every: bool = False) -> None:
    meta = load(root)
    pending = meta.get("suggestedTags", [])
    for item in chosen(pending, wanted, every):
        pending.remove(item)
        if not find(meta.setdefault("tags", []), item["tag"]):
            meta["tags"].append({**item, "added": rc.today()})
        print(f"accepted tag: {item['tag']}")
    save(root, meta)


def command_reject(root: Path, wanted: list[str], every: bool = False) -> None:
    meta = load(root)
    pending = meta.get("suggestedTags", [])
    rejected = meta.setdefault("rejectedTags", [])
    for item in chosen(pending, wanted, every):
        pending.remove(item)
        if item["tag"].casefold() not in {name.casefold() for name in rejected}:
            rejected.append(item["tag"])
        print(f"rejected tag: {item['tag']}")
    save(root, meta)


def command_list(root: Path) -> None:
    meta = load(root)
    tags = meta.get("tags", [])
    print(f"{meta.get('name', root.name)} ({meta.get('type')}): {len(tags)} tags")
    for item in tags:
        print(f"  {item['tag']}" + (f"  - {item['why']}" if item.get("why") else ""))
    if meta.get("suggestedTags"):
        print("proposed, not accepted yet:")
        for item in meta["suggestedTags"]:
            print(f"  ? {item['tag']}  - {item['why']}")
    if not tags and not meta.get("suggestedTags"):
        print('  none yet: rc tags add "<tag>", or rc tags suggest to propose them from the profile\'s material')


def main() -> int:
    parser = argparse.ArgumentParser(prog="rc tags")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    add = commands.add_parser("add")
    add.add_argument("tag")
    add.add_argument("--why", default="")
    commands.add_parser("remove").add_argument("tag")
    rename = commands.add_parser("rename")
    rename.add_argument("old")
    rename.add_argument("new")
    commands.add_parser("suggest")
    for name in ("accept", "reject"):
        sub = commands.add_parser(name)
        sub.add_argument("tags", nargs="*")
        sub.add_argument("--all", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "list":
            command_list(root)
        elif args.command == "add":
            command_add(root, args.tag, args.why)
        elif args.command == "remove":
            command_remove(root, args.tag)
        elif args.command == "rename":
            command_rename(root, args.old, args.new)
        elif args.command == "suggest":
            command_suggest(root)
        elif args.command == "accept":
            command_accept(root, args.tags, args.all)
        else:
            command_reject(root, args.tags, args.all)
    except (rc.RcError, rc.providers.ProviderError, OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
