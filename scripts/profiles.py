#!/usr/bin/env python3
"""rc profile new <id> --name "..." --type company|personal [--description "..."] | list | show <id> | edit <id> ...
| scope <id> | accept <id>: the profiles of an instance.

A profile is whom the RC scouts and researches for (docs/decisions/0015-profiles.md): a company, a product line or a
person. profiles/<id>/ holds profile.json (name, description, type, interest tags) and the profile's own data -
inbox/, catalog/sources/, sources/, knowledge/, research/ - laid out like an instance's, so the ingest and research
runners work on it unchanged. Settings, roles, adapters and skills stay the instance's.

The type sets the licence rule: a company profile may use only permissive licences, a personal one any
(templates/licences.json, scripts/runner/licences.py). scope.md is optional: a longer context document for profiles
that need one.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TYPES = ("company", "personal")
FOLDER = "profiles"
META = "profile.json"
SECTIONS = ("Who", "Products and processes", "Hard constraints", "How value is measured", "Out of scope",
            "Scouting lens", "Source preferences")
DATA = ("inbox", "catalog/sources", "sources", "knowledge/digests", "knowledge/profile", "research")
PLACEHOLDER = re.compile(r"<[^>\n]+>")


def folder(root: Path, identifier: str) -> Path:
    if not ID.fullmatch(identifier):
        raise ValueError(f"profile id must be lowercase hyphen-case: {identifier}")
    return root / FOLDER / identifier


def ids(root: Path) -> list[str]:
    return sorted(path.parent.name for path in (root / FOLDER).glob(f"*/{META}"))


def load(root: Path, identifier: str) -> dict[str, Any]:
    if identifier not in ids(root):
        raise ValueError(f"no profile {identifier}; rc profile list shows them")
    return json.loads((folder(root, identifier) / META).read_text(encoding="utf-8"))


def save(root: Path, meta: dict[str, Any]) -> None:
    (folder(root, meta["id"]) / META).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def meta_problems(meta: Any, name: str) -> list[str]:
    """What profile.json must hold: its folder's id, a name, a type and a list of tags."""
    if not isinstance(meta, dict):
        return [f"{name}/{META} must be an object"]
    problems = []
    if meta.get("id") != name:
        problems.append(f"{name}/{META}: id must equal the folder name")
    if not str(meta.get("name", "")).strip():
        problems.append(f"{name}/{META}: needs a name")
    if meta.get("type") not in TYPES:
        problems.append(f"{name}/{META}: type must be one of {', '.join(TYPES)}")
    tags = meta.get("tags", [])
    if not isinstance(tags, list):
        problems.append(f"{name}/{META}: tags must be a list")
    elif any(not isinstance(tag, dict) or not str(tag.get("tag", "")).strip() for tag in tags):
        problems.append(f"{name}/{META}: every tag is an object with its tag text (rc tags add)")
    return problems


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[index].strip(): parts[index + 1].strip() for index in range(1, len(parts) - 1, 2)}


def status(text: str) -> str:
    match = re.search(r"^Status:\s*(\S+)", text, flags=re.MULTILINE)
    return match.group(1) if match else "unknown"


def scope_problems(text: str) -> list[str]:
    found = sections(text)
    problems = []
    for name in SECTIONS:
        body = found.get(name, "")
        if not body:
            problems.append(f"section '## {name}' is missing or empty")
        elif PLACEHOLDER.search(body):
            problems.append(f"section '## {name}' still holds a <placeholder>")
    return problems


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def command_new(root: Path, identifier: str, name: str, kind: str, description: str = "") -> None:
    if not (root / "research-center.json").is_file():
        raise ValueError("profiles live in an instance; this is the template")
    if kind not in TYPES:
        raise ValueError(f"type must be one of {', '.join(TYPES)}")
    target = folder(root, identifier)
    if target.exists():
        raise ValueError(f"profile already exists: {identifier}")
    for data in DATA:
        (target / data).mkdir(parents=True, exist_ok=True)
        (target / data / ".gitkeep").touch()
    save(root, {"schemaVersion": 1, "id": identifier, "name": one_line(name), "description": one_line(description),
                "type": kind, "tags": [], "createdAt": datetime.date.today().isoformat()})
    print(f"created {FOLDER}/{identifier}/ ({kind}); add interest tags, or drop material into {FOLDER}/{identifier}/inbox/")


def command_edit(root: Path, identifier: str, name: str | None, kind: str | None, description: str | None) -> None:
    meta = load(root, identifier)
    if kind is not None and kind not in TYPES:
        raise ValueError(f"type must be one of {', '.join(TYPES)}")
    meta.update({key: one_line(value) for key, value in (("name", name), ("description", description), ("type", kind)) if value is not None})
    save(root, meta)
    print(f"updated {FOLDER}/{identifier}/{META}")


def command_scope(root: Path, identifier: str) -> None:
    """Start the optional longer context document from templates/scope.md."""
    meta = load(root, identifier)
    path = folder(root, identifier) / "scope.md"
    if path.exists():
        raise ValueError(f"{FOLDER}/{identifier}/scope.md already exists")
    template = (root / "templates" / "scope.md").read_text(encoding="utf-8")
    path.write_text(template.replace("<title>", meta["name"]).replace("<profile-id>", identifier), encoding="utf-8", newline="\n")
    print(f"created {FOLDER}/{identifier}/scope.md; fill it with the grill-profile skill, then rc profile accept {identifier}")


def summary(root: Path, identifier: str) -> dict[str, Any]:
    target = folder(root, identifier)
    meta = load(root, identifier)
    scope = (target / "scope.md").read_text(encoding="utf-8") if (target / "scope.md").is_file() else None
    return {**meta, "scope": status(scope) if scope is not None else "none",
            "sources": len(list((target / "catalog" / "sources").glob("*.json"))),
            "topics": sorted(path.parent.name for path in (target / "research").glob("*/brief.md")),
            "problems": scope_problems(scope) if scope is not None else []}


def command_accept(root: Path, identifier: str) -> None:
    path = folder(root, identifier) / "scope.md"
    if not path.is_file():
        raise ValueError(f"{FOLDER}/{identifier} has no scope.md; start one with rc profile scope {identifier}")
    text = path.read_text(encoding="utf-8")
    problems = scope_problems(text)
    if problems:
        raise ValueError("scope is not ready:\n" + "\n".join(f"- {problem}" for problem in problems))
    path.write_text(re.sub(r"^Status:\s*\S+", "Status: accepted", text, count=1, flags=re.MULTILINE), encoding="utf-8", newline="\n")
    print(f"accepted {FOLDER}/{identifier}/scope.md")


def main() -> int:
    parser = argparse.ArgumentParser(prog="rc profile")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new")
    new.add_argument("id")
    new.add_argument("--name", required=True)
    new.add_argument("--type", required=True, choices=TYPES)
    new.add_argument("--description", default="")
    commands.add_parser("list")
    edit = commands.add_parser("edit")
    edit.add_argument("id")
    edit.add_argument("--name")
    edit.add_argument("--type", choices=TYPES)
    edit.add_argument("--description")
    for name in ("show", "scope", "accept"):
        commands.add_parser(name).add_argument("id")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "new":
            command_new(root, args.id, args.name, args.type, args.description)
        elif args.command == "edit":
            command_edit(root, args.id, args.name, args.type, args.description)
        elif args.command == "list":
            if not ids(root):
                print('No profiles yet. Create one with: rc profile new <id> --name "..." --type company|personal')
            for identifier in ids(root):
                item = summary(root, identifier)
                print(f"{identifier:<20} {item['type']:<9} {len(item['tags'])} tags, {item['sources']} sources, "
                      f"{len(item['topics'])} topics  {item['name']}")
        elif args.command == "show":
            item = summary(root, args.id)
            print(f"{item['id']}: {item['name']} ({item['type']})")
            print(f"  description: {item['description'] or '(none yet)'}")
            print(f"  tags: {', '.join(tag['tag'] if isinstance(tag, dict) else str(tag) for tag in item['tags']) or '(none yet)'}")
            print(f"  sources: {item['sources']}\n  topics: {', '.join(item['topics']) or 'none'}")
            print(f"  scope.md: {item['scope']}")
            for problem in item["problems"]:
                print(f"  to finish the scope: {problem}")
        elif args.command == "scope":
            command_scope(root, args.id)
        else:
            load(root, args.id)
            command_accept(root, args.id)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
