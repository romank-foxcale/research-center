#!/usr/bin/env python3
"""./rc sources: the source adapters the research runner searches besides the web.

  list                                   the adapters, what each covers and its filters
  search <adapter> <query> [--filter k=v] [--since YYYY-MM-DD] [--limit N] [--json] [--log PATH]
  related <adapter> <id> --direction backward|forward [--limit N] [--json]

Adapters run here, in the runner, never inside an agent (docs/decisions/0007-source-adapters.md). Each search is
appended to a searches log (research/<topic>/searches.json in a run) with its exact query, filters, date and
result count, so every search can be repeated and reported.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "adapters"), str(HERE.parent / "runner")]
import kit  # noqa: E402

ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
DEFAULT_LIMIT = 20


def adapters_dir(root: Path) -> Path:
    """An instance's own catalog; the template's defaults when run in the template itself."""
    return root / "catalog" / "adapters" if (root / "research-center.json").is_file() else root / "templates" / "adapters"


def descriptors(root: Path) -> dict[str, dict[str, Any]]:
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(adapters_dir(root).glob("*.json"))}


def descriptor(root: Path, identifier: str) -> dict[str, Any]:
    if not ID.fullmatch(identifier):
        raise ValueError(f"adapter id {identifier!r} must be lowercase hyphen-case")
    known = descriptors(root)
    if identifier not in known:
        raise ValueError(f"unknown adapter {identifier}; known: {', '.join(known) or 'none'}")
    return known[identifier]


def module(spec: dict[str, Any]):
    if not ID.fullmatch(spec["module"].replace("_", "-")):
        raise ValueError(f"adapter {spec['id']}: module {spec['module']!r} is not a plain module name")
    return importlib.import_module(spec["module"])


def options(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """What an adapter may know: its rate limit, its key from the environment, and the polite-pool contact
    email only when the user set research.contactEmail. Nothing else of the instance reaches a third party."""
    settings_path = root / "research-center.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    found = {"interval": float(spec.get("rateLimit", 1.0)), "contactEmail": settings.get("research", {}).get("contactEmail") or None}
    if spec.get("needsKeyEnv"):
        key = os.environ.get(spec["needsKeyEnv"])
        if not key:
            raise kit.AdapterError(f"{spec['id']} needs the environment variable {spec['needsKeyEnv']}; it is never stored in the repo")
        found["key"] = key
    return found


def log_search(log: Path | None, entry: dict[str, Any]) -> None:
    if log is None:
        return
    entries = json.loads(log.read_text(encoding="utf-8")) if log.is_file() else []
    entries.append(entry)
    log.parent.mkdir(parents=True, exist_ok=True)
    temporary = log.with_suffix(log.suffix + ".tmp")
    temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(log)


def search(root: Path, identifier: str, query: str, filters: dict[str, str] | None = None, since: str | None = None,
           limit: int = DEFAULT_LIMIT, log: Path | None = None) -> list[dict[str, Any]]:
    """Run one adapter query and log it. A failing adapter is logged with status error and raises AdapterError;
    it never silently returns nothing."""
    spec = descriptor(root, identifier)
    filters = dict(filters or {})
    unknown = sorted(set(filters) - set(spec.get("filters", {})))
    if unknown:
        raise ValueError(f"{identifier} has no filter {', '.join(unknown)}; it has: {', '.join(spec.get('filters', {})) or 'none'}")
    if since:
        datetime.date.fromisoformat(since)
    entry = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "adapter": identifier,
             "query": query, "filters": filters, "since": since, "limit": limit}
    try:
        found = module(spec).search(query, filters, since, limit, options(root, spec))
    except kit.AdapterError as error:
        log_search(log, {**entry, "status": "error", "count": 0, "error": str(error)[:300]})
        raise
    log_search(log, {**entry, "status": "ok", "count": len(found)})
    return found


def related(root: Path, identifier: str, item: dict[str, Any], direction: str, limit: int = DEFAULT_LIMIT,
            log: Path | None = None) -> list[dict[str, Any]]:
    """The works a record cites (backward) or that cite it (forward), for adapters that support it."""
    spec = descriptor(root, identifier)
    if direction not in kit.DIRECTIONS:
        raise ValueError(f"direction must be one of {kit.DIRECTIONS}")
    if not spec.get("related"):
        raise ValueError(f"{identifier} cannot follow references or citations")
    entry = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "adapter": identifier,
             "related": item["key"], "direction": direction, "limit": limit}
    try:
        found = module(spec).related(item, direction, limit, options(root, spec))
    except kit.AdapterError as error:
        log_search(log, {**entry, "status": "error", "count": 0, "error": str(error)[:300]})
        raise
    log_search(log, {**entry, "status": "ok", "count": len(found)})
    return found


def merge(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per key, the first seen kept; every adapter that found it is listed in foundBy."""
    merged: dict[str, dict[str, Any]] = {}
    for item in records:
        kept = merged.setdefault(item["key"], {**item, "foundBy": []})
        if item["adapter"] not in kept["foundBy"]:
            kept["foundBy"].append(item["adapter"])
    return list(merged.values())


def show(records: list[dict[str, Any]]) -> None:
    for number, item in enumerate(records, 1):
        who = ", ".join(item["authors"][:3]) + (" et al." if len(item["authors"]) > 3 else "")
        print(f"{number:>3}. {item['title']}")
        print(f"     {item['evidenceType']} | {item['date'] or 'undated'}{' | ' + who if who else ''}")
        print(f"     {item['url']}")
        if item["extra"].get("retracted"):
            print("     RETRACTED")


def parse_filters(values: list[str]) -> dict[str, str]:
    filters = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--filter takes key=value, not {value!r}")
        key, _, setting = value.partition("=")
        filters[key.strip()] = setting.strip()
    return filters


def main() -> int:
    parser = argparse.ArgumentParser(prog="./rc sources")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    find = commands.add_parser("search")
    find.add_argument("adapter")
    find.add_argument("query", nargs="+")
    find.add_argument("--filter", action="append", default=[])
    find.add_argument("--since")
    find.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    find.add_argument("--json", action="store_true")
    find.add_argument("--log", type=Path)
    follow = commands.add_parser("related")
    follow.add_argument("adapter")
    follow.add_argument("id", help="the adapter's own id of the record, e.g. an OpenAlex W-id")
    follow.add_argument("--direction", choices=kit.DIRECTIONS, required=True)
    follow.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    follow.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    # Titles come in every script; a console that cannot show one prints a placeholder instead of crashing.
    sys.stdout.reconfigure(errors="replace")
    try:
        if args.command == "list":
            for identifier, spec in descriptors(root).items():
                print(f"{identifier:<12} {spec['family']:<10} {spec['covers']}")
                for name, help_text in spec.get("filters", {}).items():
                    print(f"{'':<24}--filter {name}=...  {help_text}")
            return 0
        if args.command == "search":
            found = search(root, args.adapter, " ".join(args.query), parse_filters(args.filter), args.since, args.limit,
                           args.log.resolve() if args.log else None)
        else:
            stub = {"key": f"{args.adapter}:{args.id}", "title": args.id, "extra": {"openalexId": args.id}}
            found = related(root, args.adapter, stub, args.direction, args.limit)
    except (ValueError, kit.AdapterError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        show(found)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
