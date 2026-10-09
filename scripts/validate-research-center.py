#!/usr/bin/env python3
"""Validate the Research Center contract: settings and roles, and in an instance its committed data.

Template (no research-center.json): templates/research-center.json and templates/agents are checked, and the
template must hold no sources, knowledge or research. Instance: catalog/agents and research-center.json, plus
every source manifest, every knowledge note's evidence, every report's citations, and a secret scan.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "ingest"), str(HERE / "runner")]
import secrets_scan  # noqa: E402

_spec = importlib.util.spec_from_file_location("validate_knowledge", HERE / "validate-knowledge.py")
_knowledge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_knowledge)


def parse_frontmatter(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    return _knowledge.parse_frontmatter(Path("note.md"), text)

PROVIDERS = ("claude", "codex", "cursor")
ACCESS = ("read-only", "web-read", "connector-read")
CONNECTORS = ("notion", "gdrive")
SINGLE_ROLES = {
    "connectorReader": "connector-read",
    "digester": "read-only",
    "profiler": "read-only",
    "sourcePlanner": "read-only",
    "analyst": "read-only",
    "judge": "read-only",
    "applier": "read-only",
    "reporter": "read-only",
}
LIST_ROLES = {"researchers": "web-read", "sceptics": "read-only"}
NUMBERS = {
    "budget": ("ingestCalls", "researchCalls"),
    "ingest": ("maxFileBytes", "maxSourceBytes", "chunkBytes"),
    "research": ("maxSourcesPerResearcher",),
}
DATA_DIRS = ("sources", "knowledge", "research", "catalog/sources")
KINDS = ("folder", "git", "url", "notion", "gdrive")
CLAIM = re.compile(r"\[(C\d+)\]")
NOTE_FIELDS = ("id", "title", "status", "summary", "verified_at")


def load(path: Path, errors: list[str], root: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{path.relative_to(root)}: {error}")
        return None


def check_role(root: Path, path: Path, role: dict[str, Any], errors: list[str]) -> None:
    name = path.relative_to(root).as_posix()
    if role.get("id") != path.stem:
        errors.append(f"{name}: id must equal the file name")
    if role.get("provider") not in PROVIDERS:
        errors.append(f"{name}: provider must be one of {PROVIDERS}")
    if role.get("access") not in ACCESS:
        errors.append(f"{name}: access must be one of {ACCESS}")
    if not role.get("model"):
        errors.append(f"{name}: model is empty")
    if role.get("provider") == "cursor" and role.get("access") != "read-only":
        errors.append(f"{name}: cursor roles can only be read-only")
    if role.get("access") == "connector-read":
        if role.get("provider") != "claude":
            errors.append(f"{name}: only claude roles can read connectors")
        if not role.get("connectors") or set(role["connectors"]) - set(CONNECTORS):
            errors.append(f"{name}: connectors must be a non-empty subset of {CONNECTORS}")
    for skill in role.get("skills", []):
        if not (root / ".agents" / "skills" / skill / "SKILL.md").is_file():
            errors.append(f"{name}: skill {skill} does not exist")


def check_settings(root: Path, settings: dict[str, Any], roles_dir: Path, errors: list[str], label: str) -> None:
    roles: dict[str, dict[str, Any]] = {}
    for path in sorted(roles_dir.glob("*.json")):
        role = load(path, errors, root)
        if isinstance(role, dict):
            check_role(root, path, role, errors)
            roles[path.stem] = role
    for group, keys in NUMBERS.items():
        for key in keys:
            value = settings.get(group, {}).get(key)
            if not isinstance(value, int) or value <= 0:
                errors.append(f"{label}: {group}.{key} must be a positive integer")
    pipeline = settings.get("pipeline", {})
    slots = [(slot, pipeline.get(slot), access) for slot, access in SINGLE_ROLES.items()]
    for slot, access in LIST_ROLES.items():
        value = pipeline.get(slot)
        if not isinstance(value, list) or not value:
            errors.append(f"{label}: pipeline.{slot} must be a non-empty list of roles")
            continue
        slots += [(slot, item, access) for item in value]
    for slot, identifier, access in slots:
        if identifier not in roles:
            errors.append(f"{label}: pipeline.{slot} names role {identifier!r}, which is not in {roles_dir.relative_to(root)}")
        elif roles[identifier].get("access") != access:
            errors.append(f"{label}: pipeline.{slot} needs {access} access; role {identifier} has {roles[identifier].get('access')}")


def check_sources(root: Path, errors: list[str]) -> None:
    catalog = {path.stem: load(path, errors, root) for path in sorted((root / "catalog" / "sources").glob("*.json"))}
    for identifier, descriptor in catalog.items():
        if not isinstance(descriptor, dict) or descriptor.get("id") != identifier or descriptor.get("kind") not in KINDS:
            errors.append(f"catalog/sources/{identifier}.json: id must equal the file name and kind be one of {KINDS}")
    for directory in sorted(path for path in (root / "sources").glob("*") if path.is_dir()):
        name = directory.relative_to(root).as_posix()
        if directory.name not in catalog:
            errors.append(f"{name}: no catalog/sources/{directory.name}.json")
        manifest = load(directory / "manifest.json", errors, root) if (directory / "manifest.json").is_file() else None
        if manifest is None:
            errors.append(f"{name}: manifest.json is missing")
            continue
        listed = set(manifest.get("files", {}))
        present = {path.relative_to(directory / "text").as_posix() for path in (directory / "text").rglob("*") if path.is_file()}
        errors += [f"{name}/text/{stored}: in the manifest but missing" for stored in sorted(listed - present)]
        errors += [f"{name}/text/{stored}: not in the manifest" for stored in sorted(present - listed)]
        for path in sorted(directory.rglob("*")):
            if path.is_file() and b"\0" in path.read_bytes()[:8192]:
                errors.append(f"{path.relative_to(root).as_posix()}: binary file; commit extracted text only")


def check_notes(root: Path, errors: list[str]) -> None:
    for note in sorted((root / "knowledge").rglob("*.md")):
        name = note.relative_to(root).as_posix()
        try:
            scalars, lists = parse_frontmatter(note.read_text(encoding="utf-8"))
        except ValueError as error:
            errors.append(f"{name}: {error}")
            continue
        errors += [f"{name}: missing frontmatter field '{field}'" for field in NOTE_FIELDS if not scalars.get(field)]
        for field in ("evidence", "relations"):
            if not lists.get(field):
                errors.append(f"{name}: '{field}' must list at least one path")
            for value in lists.get(field, []):
                if not (root / value).exists():
                    errors.append(f"{name}: broken {field} path '{value}'")


def check_reports(root: Path, errors: list[str]) -> None:
    for directory in sorted(path for path in (root / "research").glob("*") if path.is_dir()):
        name = directory.relative_to(root).as_posix()
        if not (directory / "brief.md").is_file():
            errors.append(f"{name}: brief.md is missing")
        report = directory / "report.md"
        if not report.is_file():
            continue
        claims = load(directory / "claims.json", errors, root) or {}
        judgement = load(directory / "judgement.json", errors, root) or {}
        known = {claim["id"] for claim in claims.get("claims", [])}
        verdicts = {item["claim"]: item["verdict"] for item in judgement.get("claims", [])}
        body = report.read_text(encoding="utf-8").split("\n## Evidence\n", 1)[0]
        for claim in sorted(set(CLAIM.findall(body))):
            if claim not in known:
                errors.append(f"{name}/report.md: cites {claim}, which is not in claims.json")
            elif verdicts.get(claim) in ("REFUTED", "UNSUPPORTED"):
                errors.append(f"{name}/report.md: relies on {claim}, judged {verdicts[claim]}")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    settings_path = root / "research-center.json"
    if settings_path.is_file():
        settings = load(settings_path, errors, root)
        if isinstance(settings, dict):
            check_settings(root, settings, root / "catalog" / "agents", errors, "research-center.json")
        check_sources(root, errors)
        check_notes(root, errors)
        check_reports(root, errors)
        errors += secrets_scan.scan(root, ["sources", "knowledge", "research", "catalog"])
    else:
        template = load(root / "templates" / "research-center.json", errors, root)
        if isinstance(template, dict):
            check_settings(root, template, root / "templates" / "agents", errors, "templates/research-center.json")
        for folder in DATA_DIRS:
            if any(path.is_file() and path.name != ".gitkeep" for path in (root / folder).rglob("*")):
                errors.append(f"{folder}/: the template ships no data; ingest and research only in an instance")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors = validate(root)
    if errors:
        print("research center validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"research center validation passed ({'instance' if (root / 'research-center.json').is_file() else 'template'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
