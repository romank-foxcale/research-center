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
sys.path[:0] = [str(HERE), str(HERE / "ingest"), str(HERE / "runner"), str(HERE / "sources")]
import kit  # noqa: E402
import secrets_scan  # noqa: E402
import profiles  # noqa: E402

_spec = importlib.util.spec_from_file_location("validate_knowledge", HERE / "validate-knowledge.py")
_knowledge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_knowledge)


def parse_frontmatter(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    return _knowledge.parse_frontmatter(Path("note.md"), text)

PROVIDERS = ("claude", "codex")
# The same lifecycle as a Control Center's control-center.json; rc-kit list shows it.
STATUSES = ("discovery", "adapting", "ready")
ACCESS = ("read-only", "web-read", "connector-read")
CONNECTORS = ("notion", "gdrive")
SINGLE_ROLES = {
    "connectorReader": "connector-read",
    "digester": "read-only",
    "profiler": "read-only",
    "tagger": "read-only",
    "scoutTriage": "read-only",
    "scoutEvaluator": "read-only",
    "scoutSceptic": "read-only",
    "sourcePlanner": "read-only",
    "screener": "read-only",
    "analyst": "read-only",
    "judge": "read-only",
    "applier": "read-only",
    "reporter": "read-only",
}
LIST_ROLES = {"researchers": "web-read", "sceptics": "read-only"}
NUMBERS = {
    "budget": ("ingestCalls", "researchCalls"),
    "ingest": ("maxFileBytes", "maxSourceBytes", "chunkBytes"),
    "research": ("maxSourcesPerResearcher", "resultsPerQuery", "screenBatch"),
}
COUNTS = ("snowballDepth", "snowballSeeds", "snowballPerSeed")  # optional; 0 is allowed
GRADES = ("A", "B", "C", "D", "E", "F")
CERTAINTIES = ("very low", "low", "moderate", "high")
DATA_DIRS = ("sources", "knowledge", "research", "catalog/sources", "profiles", "usecases")
KINDS = ("folder", "git", "url", "notion", "gdrive")
CLAIM = re.compile(r"\[(C\d+(?:\s*[,;]\s*C\d+)*)\]")
ADAPTER_FIELDS = {"schemaVersion": int, "id": str, "module": str, "family": str, "covers": str, "evidenceTypes": list,
                  "queryHelp": str, "filters": dict, "watchable": bool, "related": bool, "rateLimit": (int, float)}
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
    if settings.get("status") not in STATUSES:
        errors.append(f"{label}: status must be one of {STATUSES} (discovery when created, ready once bootstrapped)")
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
    refresh = settings.get("budget", {}).get("refreshCalls", 16)
    if not isinstance(refresh, int) or isinstance(refresh, bool) or refresh <= 0:
        errors.append(f"{label}: budget.refreshCalls must be a positive integer")
    for key in COUNTS:
        value = settings.get("research", {}).get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{label}: research.{key} must be a whole number, 0 or more (0 turns snowballing off)")
    email = settings.get("research", {}).get("contactEmail", "")
    if not isinstance(email, str) or (email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)):
        errors.append(f"{label}: research.contactEmail must be empty or an email address the user chose to share")


def check_evidence_types(root: Path, path: Path, errors: list[str]) -> None:
    """The evidence types cover exactly the adapters' vocabulary, each with a reliability ceiling and a half-life."""
    name = path.relative_to(root).as_posix()
    data = load(path, errors, root) if path.is_file() else None
    if not isinstance(data, dict) or not isinstance(data.get("types"), list):
        errors.append(f"{name}: missing, or without a types list")
        return
    ids = [item.get("id") for item in data["types"]]
    if sorted(ids) != sorted(kit.EVIDENCE_TYPES):
        errors.append(f"{name}: types must be exactly {kit.EVIDENCE_TYPES}; tune their ceilings and half-lives, not the ids")
    for item in data["types"]:
        if item.get("reliabilityCeiling") not in GRADES[:5]:
            errors.append(f"{name}: {item.get('id')}: reliabilityCeiling must be one of {GRADES[:5]}")
        if not isinstance(item.get("halfLifeDays"), int) or isinstance(item.get("halfLifeDays"), bool) or item["halfLifeDays"] <= 0:
            errors.append(f"{name}: {item.get('id')}: halfLifeDays must be a positive whole number")


def check_adapters(root: Path, directory: Path, errors: list[str]) -> None:
    """Every adapter descriptor names an existing module and only known families and evidence types."""
    for path in sorted(directory.glob("*.json")):
        name = path.relative_to(root).as_posix()
        spec = load(path, errors, root)
        if not isinstance(spec, dict):
            continue
        for field, kind in ADAPTER_FIELDS.items():
            value = spec.get(field)
            # bool is an int in Python; a flag where a number belongs (or the reverse) is still wrong.
            if not isinstance(value, kind) or isinstance(value, bool) != (kind is bool):
                errors.append(f"{name}: {field} must be {kind.__name__ if isinstance(kind, type) else 'a number'}")
        if spec.get("id") != path.stem:
            errors.append(f"{name}: id must equal the file name")
        if spec.get("family") not in kit.FAMILIES:
            errors.append(f"{name}: family must be one of {kit.FAMILIES}")
        unknown = set(spec.get("evidenceTypes") or []) - set(kit.EVIDENCE_TYPES)
        if unknown or not spec.get("evidenceTypes"):
            errors.append(f"{name}: evidenceTypes must be a non-empty subset of {kit.EVIDENCE_TYPES}")
        module = str(spec.get("module", ""))
        own = root / "catalog" / "adapters" / "code" / f"{module}.py"
        if not re.fullmatch(r"[a-z0-9_]+", module) or not ((HERE / "sources" / "adapters" / f"{module}.py").is_file() or own.is_file()):
            errors.append(f"{name}: module {module!r} is neither in scripts/sources/adapters/ nor in catalog/adapters/code/")
        if not isinstance(spec.get("retractions", False), bool):
            errors.append(f"{name}: retractions must be true or false")
        for field in ("needsKeyEnv", "optionalKeyEnv"):
            if spec.get(field) is not None and not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(spec[field])):
                errors.append(f"{name}: {field} must be null or an environment variable name; keys are never stored")


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
        for answer in judgement.get("answers", []):
            if answer.get("certainty") not in CERTAINTIES:
                errors.append(f"{name}/judgement.json: the answer to {answer.get('question')} has no certainty")
            for entry in [*answer.get("downgrades", []), *answer.get("upgrades", [])]:
                if not str(entry.get("reason", "")).strip():
                    errors.append(f"{name}/judgement.json: a {entry.get('domain')} grade of {answer.get('question')} gives no reason")
        cited = {claim for group in CLAIM.findall(body) for claim in re.split(r"\s*[,;]\s*", group)}
        for claim in sorted(cited):
            if claim not in known:
                errors.append(f"{name}/report.md: cites {claim}, which is not in claims.json")
            elif verdicts.get(claim) in ("REFUTED", "UNSUPPORTED"):
                errors.append(f"{name}/report.md: relies on {claim}, judged {verdicts[claim]}")


def check_profile(root: Path, space: Path, errors: list[str]) -> None:
    """A profile names itself after its folder, with a name, a type and tags; an optional scope.md, once accepted,
    has every section filled."""
    name = space.relative_to(root).as_posix()
    meta = load(space / profiles.META, errors, root)
    if meta is not None:
        errors += [problem.replace(f"{space.name}/", f"{name}/", 1) for problem in profiles.meta_problems(meta, space.name)]
    scope = space / "scope.md"
    if scope.is_file():
        text = scope.read_text(encoding="utf-8")
        if re.search(r"^Status:\s*accepted", text, flags=re.MULTILINE):
            errors += [f"{name}/scope.md: {problem}" for problem in profiles.scope_problems(text)]


def check_licences(root: Path, path: Path, errors: list[str]) -> None:
    """The licence table: every class a list of SPDX ids, no id in two classes, a reason for every unusable class."""
    data = load(path, errors, root)
    if not isinstance(data, dict) or not isinstance(data.get("classes"), dict):
        errors.append(f"{path.relative_to(root).as_posix()}: needs a classes object")
        return
    seen: dict[str, str] = {}
    for kind, members in data["classes"].items():
        for member in members if isinstance(members, list) else []:
            key = str(member).lower()
            if key in seen:
                errors.append(f"{path.relative_to(root).as_posix()}: {member} is in both {seen[key]} and {kind}")
            seen[key] = kind
        if kind != "permissive" and kind not in data.get("reasons", {}):
            errors.append(f"{path.relative_to(root).as_posix()}: class {kind} needs a reason")
    if "unknown" not in data.get("reasons", {}):
        errors.append(f"{path.relative_to(root).as_posix()}: needs a reason for unknown licences")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    settings_path = root / "research-center.json"
    if settings_path.is_file():
        settings = load(settings_path, errors, root)
        if isinstance(settings, dict):
            check_settings(root, settings, root / "catalog" / "agents", errors, "research-center.json")
        check_adapters(root, root / "catalog" / "adapters", errors)
        if (root / "catalog" / "evidence-types.json").is_file():
            check_evidence_types(root, root / "catalog" / "evidence-types.json", errors)
        errors += secrets_scan.scan(root, ["catalog"])
        if (root / "usecases").is_dir():
            errors.append("usecases/ is the layout from before profiles; run rc upgrade from the template to move it to profiles/")
        # The instance root holds data when it has no profiles; every profile holds its own (ADR 0015).
        for space in [root, *sorted(path.parent for path in (root / profiles.FOLDER).glob(f"*/{profiles.META}"))]:
            if space != root:
                check_profile(root, space, errors)
            check_sources(space, errors)
            check_notes(space, errors)
            check_reports(space, errors)
            errors += [f"{space.relative_to(root).as_posix()}/{error}" if space != root else error
                       for error in secrets_scan.scan(space, ["sources", "knowledge", "research", "catalog/sources"])]
    else:
        template = load(root / "templates" / "research-center.json", errors, root)
        if isinstance(template, dict):
            check_settings(root, template, root / "templates" / "agents", errors, "templates/research-center.json")
        check_adapters(root, root / "templates" / "adapters", errors)
        check_evidence_types(root, root / "templates" / "evidence-types.json", errors)
        check_licences(root, root / "templates" / "licences.json", errors)
        for pack in sorted((root / "templates" / "packs").glob("*/pack.json")):
            data = load(pack, errors, root)
            if not isinstance(data, dict) or data.get("id") != pack.parent.name or not data.get("description"):
                errors.append(f"{pack.relative_to(root).as_posix()}: id must equal the folder name, with a description")
            if not any((pack.parent / "adapters").glob("*.json")):
                errors.append(f"{pack.relative_to(root).as_posix()}: a pack ships at least one adapter in adapters/")
            check_adapters(root, pack.parent / "adapters", errors)
        if not any((root / "templates" / "adapters").glob("*.json")):
            errors.append("templates/adapters/: the template must ship the default source adapters")
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
