#!/usr/bin/env python3
"""./rc sources: the source adapters the research runner searches besides the web.

  list                                   the adapters, what each covers and its filters
  search <adapter> <query> [--filter k=v] [--since YYYY-MM-DD] [--limit N] [--json] [--log PATH]
  related <adapter> <id> --direction backward|forward [--limit N] [--json]
  packs | enable <pack> | disable <pack>  domain packs (medicine, software, ...) an instance turns on as topics need them
  new <adapter> --family F --evidence-type T  scaffold your own adapter for a site or API, ready to edit and test
  test [<adapter>]                       replay adapters' fixtures offline

Adapters run here, in the runner, never inside an agent (docs/decisions/0007-source-adapters.md). Each search is
appended to a searches log (research/<topic>/searches.json in a run) with its exact query, filters, date and
result count, so every search can be repeated and reported.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import importlib.util
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


def module(spec: dict[str, Any], root: Path | None = None):
    """An adapter's code: scripts/sources/adapters/<module>.py, or the instance's own catalog/adapters/code/<module>.py."""
    if not ID.fullmatch(spec["module"].replace("_", "-")):
        raise ValueError(f"adapter {spec['id']}: module {spec['module']!r} is not a plain module name")
    if (HERE / "adapters" / f"{spec['module']}.py").is_file() or root is None:
        return importlib.import_module(spec["module"])
    path = root / "catalog" / "adapters" / "code" / f"{spec['module']}.py"
    if not path.is_file():
        raise ValueError(f"adapter {spec['id']}: no module {spec['module']} in scripts/sources/adapters or catalog/adapters/code")
    loaded = importlib.util.spec_from_file_location(f"rc_adapter_{spec['module']}", path)
    code = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(code)
    return code


# Packs and your own adapters --------------------------------------------------------------------------------

PACKS = HERE.parent.parent / "templates" / "packs"
TEMPLATE = HERE.parent.parent / "templates" / "adapter-template"


def packs() -> dict[str, dict[str, Any]]:
    """Domain packs: adapters an instance enables when its topics need them (templates/packs/<pack>/)."""
    found = {}
    for path in sorted(PACKS.glob("*/pack.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        pack["descriptors"] = {item.stem: json.loads(item.read_text(encoding="utf-8")) for item in sorted((path.parent / "adapters").glob("*.json"))}
        found[pack["id"]] = pack
    return found


def instance_only(root: Path) -> None:
    if not (root / "research-center.json").is_file():
        raise ValueError("this changes an instance's catalog/adapters; run it in an instance, not the template")


def set_pack(root: Path, identifier: str, enabled: bool) -> list[str]:
    """Enable a pack (copy its adapter descriptors into catalog/adapters) or disable it (remove them)."""
    instance_only(root)
    known = packs()
    if identifier not in known:
        raise ValueError(f"unknown pack {identifier}; packs: {', '.join(known)}")
    target = adapters_dir(root)
    target.mkdir(parents=True, exist_ok=True)
    for name, spec in known[identifier]["descriptors"].items():
        if enabled:
            (target / f"{name}.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        else:
            (target / f"{name}.json").unlink(missing_ok=True)
    return list(known[identifier]["descriptors"])


def scaffold(root: Path, identifier: str, family: str, evidence: str) -> list[Path]:
    """Your own adapter for a site or API no adapter covers: a descriptor, a module to edit and a fixture its test
    replays, all in the instance (catalog/adapters/, catalog/adapters/code/). It passes ./rc sources test as made."""
    instance_only(root)
    if not ID.fullmatch(identifier):
        raise ValueError(f"adapter id {identifier!r} must be lowercase hyphen-case")
    name = identifier.replace("-", "_")
    taken = set(descriptors(root)) | {path.stem for path in (HERE / "adapters").glob("*.py")} | {
        adapter for pack in packs().values() for adapter in pack["descriptors"]}
    if identifier in taken or name in taken:
        raise ValueError(f"{identifier} is already an adapter id or module name")
    if family not in kit.FAMILIES or evidence not in kit.EVIDENCE_TYPES:
        raise ValueError(f"family must be one of {kit.FAMILIES} and the evidence type one of {kit.EVIDENCE_TYPES}")
    code = root / "catalog" / "adapters" / "code"
    code.mkdir(parents=True, exist_ok=True)
    written = []
    for source, target in (("adapter.json", adapters_dir(root) / f"{identifier}.json"), ("adapter.py", code / f"{name}.py"),
                           ("adapter.fixture.json", code / f"{identifier}.fixture.json")):
        text = (TEMPLATE / source).read_text(encoding="utf-8")
        for placeholder, value in (("__ID__", identifier), ("__MODULE__", name), ("__FAMILY__", family), ("__EVIDENCE__", evidence)):
            text = text.replace(placeholder, value)
        target.write_text(text, encoding="utf-8", newline="\n")
        written.append(target)
    return written


def fixture_path(root: Path, identifier: str) -> Path:
    own = root / "catalog" / "adapters" / "code" / f"{identifier}.fixture.json"
    return own if own.is_file() else HERE / "fixtures" / f"{identifier}.fixture.json"


def testable(root: Path) -> dict[str, dict[str, Any]]:
    """Every adapter there is here, keyed by id: the active ones and every pack's, enabled or not, so a pack's
    fixture can be checked before it is turned on."""
    found = {identifier: spec for pack in packs().values() for identifier, spec in pack["descriptors"].items()}
    found.update(descriptors(root))
    return found


def run_fixture(root: Path, identifier: str) -> list[str]:
    """Replay an adapter's declarative fixture offline: its canned responses answer the requests, and the records
    must match what the fixture expects. Returns the problems; empty means it passed."""
    spec = testable(root).get(identifier)
    path = fixture_path(root, identifier)
    if spec is None or not path.is_file():
        return [f"{identifier}: no adapter, or no fixture at {path.name}"]
    fixture = json.loads(path.read_text(encoding="utf-8"))

    def transport(url: str) -> tuple[bytes, str]:
        for response in fixture["responses"]:
            if response["match"] in url:
                body = response["body"]
                return (body if isinstance(body, str) else json.dumps(body)).encode("utf-8"), response.get("contentType", "application/json")
        raise kit.AdapterError(f"the fixture has no response for {url}")

    previous, kit.TRANSPORT = kit.TRANSPORT, transport
    try:
        found = module(spec, root).search(fixture["query"], fixture.get("filters", {}), fixture.get("since"), fixture.get("limit", 20),
                                          {"interval": 0, "contactEmail": None})
    except (kit.AdapterError, KeyError, TypeError, ValueError) as error:
        return [f"{identifier}: {type(error).__name__}: {error}"]
    finally:
        kit.TRANSPORT = previous
    expect, problems = fixture["expect"], []
    if "count" in expect and len(found) != expect["count"]:
        problems.append(f"{identifier}: expected {expect['count']} records, got {len(found)}")
    for field, key in (("titles", "title"), ("evidenceTypes", "evidenceType"), ("keys", "key"), ("dates", "date")):
        if field in expect and [item[key] for item in found] != expect[field]:
            problems.append(f"{identifier}: {field} {[item[key] for item in found]} != {expect[field]}")
    return problems


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
        found = module(spec, root).search(query, filters, since, limit, options(root, spec))
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
        found = module(spec, root).related(item, direction, limit, options(root, spec))
    except kit.AdapterError as error:
        log_search(log, {**entry, "status": "error", "count": 0, "error": str(error)[:300]})
        raise
    log_search(log, {**entry, "status": "ok", "count": len(found)})
    return found


def retractions(root: Path, dois: list[str], log: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Which of dois are retracted, withdrawn or removed, asked of every adapter whose descriptor says it knows
    ("retractions": true). An adapter failure is logged and raised: the caller decides how to report it."""
    found: dict[str, list[dict[str, Any]]] = {}
    if not dois:
        return found
    for identifier, spec in descriptors(root).items():
        if not spec.get("retractions"):
            continue
        entry = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "adapter": identifier,
                 "retractionCheck": len(dois)}
        try:
            result = module(spec, root).retracted(dois, options(root, spec))
        except kit.AdapterError as error:
            log_search(log, {**entry, "status": "error", "count": 0, "error": str(error)[:300]})
            raise
        log_search(log, {**entry, "status": "ok", "count": len(result)})
        found.update(result)
    return found


def merge(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per key, the first seen kept; every adapter that found it is listed in foundBy, and a
    retraction flag from any of them survives the merge."""
    merged: dict[str, dict[str, Any]] = {}
    for item in records:
        kept = merged.setdefault(item["key"], {**item, "extra": dict(item["extra"]), "foundBy": []})
        if item["adapter"] not in kept["foundBy"]:
            kept["foundBy"].append(item["adapter"])
        if item["extra"].get("retracted"):
            kept["extra"]["retracted"] = True
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
    commands.add_parser("packs")
    for name in ("enable", "disable"):
        commands.add_parser(name).add_argument("pack")
    new = commands.add_parser("new")
    new.add_argument("adapter")
    new.add_argument("--family", required=True, choices=kit.FAMILIES)
    new.add_argument("--evidence-type", required=True, choices=kit.EVIDENCE_TYPES)
    check = commands.add_parser("test")
    check.add_argument("adapter", nargs="?", help="default: every adapter with a fixture")
    args = parser.parse_args()
    root = args.root.resolve()
    # Titles come in every script; a console that cannot show one prints a placeholder instead of crashing.
    sys.stdout.reconfigure(errors="replace")
    try:
        if args.command == "packs":
            active = set(descriptors(root))
            for identifier, pack in packs().items():
                state = "enabled" if set(pack["descriptors"]) <= active else "available"
                print(f"{identifier:<12} {state:<10} {', '.join(pack['descriptors'])}: {pack['description']}")
            return 0
        if args.command in ("enable", "disable"):
            names = set_pack(root, args.pack, args.command == "enable")
            print(f"{args.command}d pack {args.pack}: {', '.join(names)} in catalog/adapters")
            return 0
        if args.command == "new":
            for path in scaffold(root, args.adapter, args.family, args.evidence_type):
                print(f"wrote {path.relative_to(root).as_posix()}")
            print(f"edit the module and its fixture, then ./rc sources test {args.adapter}")
            return 0
        if args.command == "test":
            targets = [args.adapter] if args.adapter else [identifier for identifier in testable(root) if fixture_path(root, identifier).is_file()]
            problems = [problem for identifier in targets for problem in run_fixture(root, identifier)]
            for problem in problems:
                print(f"fail: {problem}", file=sys.stderr)
            print(f"{len(targets) - len({problem.split(':')[0] for problem in problems})} of {len(targets)} adapter fixtures passed")
            return 1 if problems else 0
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
