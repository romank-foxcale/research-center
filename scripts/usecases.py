#!/usr/bin/env python3
"""rc usecase new <id> --title "..." | list | show <id> | accept <id>: the use cases of an instance.

A use case is a scoped part of the instance (docs/decisions/0013-use-case-scopes.md): usecases/<id>/ holds its
scope.md and its own data - catalog/sources/, sources/, knowledge/, research/ - laid out like an instance's, so the
ingest and research runners work on it unchanged. Settings, roles, adapters and skills stay the instance's.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SECTIONS = ("Who", "Products and processes", "Hard constraints", "How value is measured", "Out of scope",
            "Scouting lens", "Source preferences")
DATA = ("catalog/sources", "sources", "knowledge/digests", "knowledge/profile", "research")
PLACEHOLDER = re.compile(r"<[^>\n]+>")


def folder(root: Path, identifier: str) -> Path:
    if not ID.fullmatch(identifier):
        raise ValueError(f"use case id must be lowercase hyphen-case: {identifier}")
    return root / "usecases" / identifier


def ids(root: Path) -> list[str]:
    return sorted(path.parent.name for path in (root / "usecases").glob("*/usecase.json"))


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


def command_new(root: Path, identifier: str, title: str) -> None:
    if not (root / "research-center.json").is_file():
        raise ValueError("use cases live in an instance; this is the template")
    target = folder(root, identifier)
    if target.exists():
        raise ValueError(f"use case already exists: {identifier}")
    for name in DATA:
        (target / name).mkdir(parents=True, exist_ok=True)
        (target / name / ".gitkeep").touch()
    title = " ".join(title.split())
    (target / "usecase.json").write_text(json.dumps({"schemaVersion": 1, "id": identifier, "title": title,
                                                      "createdAt": datetime.date.today().isoformat()}, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")
    template = (root / "templates" / "scope.md").read_text(encoding="utf-8")
    (target / "scope.md").write_text(template.replace("<title>", title).replace("<use-case-id>", identifier),
                                     encoding="utf-8", newline="\n")
    print(f"created usecases/{identifier}/; write its scope.md with the grill-use-case skill, then rc usecase accept {identifier}")


def summary(root: Path, identifier: str) -> dict[str, object]:
    target = folder(root, identifier)
    text = (target / "scope.md").read_text(encoding="utf-8") if (target / "scope.md").is_file() else ""
    meta = json.loads((target / "usecase.json").read_text(encoding="utf-8"))
    return {"id": identifier, "title": meta.get("title", ""), "scope": status(text),
            "sources": len(list((target / "catalog" / "sources").glob("*.json"))),
            "topics": sorted(path.parent.name for path in (target / "research").glob("*/brief.md")),
            "problems": scope_problems(text)}


def command_accept(root: Path, identifier: str) -> None:
    path = folder(root, identifier) / "scope.md"
    text = path.read_text(encoding="utf-8")
    problems = scope_problems(text)
    if problems:
        raise ValueError("scope is not ready:\n" + "\n".join(f"- {problem}" for problem in problems))
    path.write_text(re.sub(r"^Status:\s*\S+", "Status: accepted", text, count=1, flags=re.MULTILINE), encoding="utf-8", newline="\n")
    print(f"accepted usecases/{identifier}/scope.md; research under it can now run")


def main() -> int:
    parser = argparse.ArgumentParser(prog="rc usecase")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new")
    new.add_argument("id")
    new.add_argument("--title", required=True)
    commands.add_parser("list")
    for name in ("show", "accept"):
        commands.add_parser(name).add_argument("id")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "new":
            command_new(root, args.id, args.title)
        elif args.command == "list":
            if not ids(root):
                print("No use cases yet. Create one with: rc usecase new <id> --title \"...\"")
            for identifier in ids(root):
                item = summary(root, identifier)
                print(f"{identifier:<24} scope {item['scope']:<9} {item['sources']} sources, {len(item['topics'])} topics  {item['title']}")
        elif args.command == "show":
            if args.id not in ids(root):
                raise ValueError(f"no use case {args.id}; rc usecase list shows them")
            item = summary(root, args.id)
            print(f"{item['id']}: {item['title']}\n  scope: usecases/{item['id']}/scope.md ({item['scope']})")
            print(f"  sources: {item['sources']}\n  topics: {', '.join(item['topics']) or 'none'}")
            for problem in item["problems"]:
                print(f"  to finish the scope: {problem}")
        else:
            if args.id not in ids(root):
                raise ValueError(f"no use case {args.id}; rc usecase list shows them")
            command_accept(root, args.id)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
