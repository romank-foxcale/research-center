#!/usr/bin/env python3
"""rc upgrade <instance> [--reset-roles] [--force]: bring an instance's template-owned files up to this template.

An instance is a copy of the template made when it was created, so it does not receive later template changes on
its own (docs/debt/instance-updates.md). This replaces what the template owns - the command line, scripts, skills,
templates and protocol docs - and leaves what the instance owns alone: sources, knowledge, research, plans, its
README and its catalog edits. Settings and roles gain what is new without losing what was set. The instance must
have no uncommitted changes, so every upgrade is one reviewable, revertible diff.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).resolve().parents[1]
# Replaced as a whole: files the instance should not have edited, and stale files in them are removed.
MIRRORED_DIRS = ("scripts", ".agents/skills", ".claude/skills", "templates", "install")
# Replaced file by file; notes the instance added in docs/ stay.
MERGED_DIRS = ("docs",)
FILES = ("rc.py", "rc", "rc.cmd", "rc.ps1", "pyproject.toml", "uv.lock", "AGENTS.md", "CLAUDE.md", "GUIDE.md",
         "BOOTSTRAP.md", ".gitattributes", ".gitignore", ".claude/settings.json")
OBSOLETE = ("flake.nix", "flake.lock", "nix")
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc")


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def merge_missing(target: dict[str, Any], seed: dict[str, Any], path: str = "") -> list[str]:
    """Add the keys seed has and target lacks, recursively; never overwrite. Returns the keys added."""
    added = []
    for key, value in seed.items():
        if key not in target:
            target[key] = value
            added.append(f"{path}{key}")
        elif isinstance(value, dict) and isinstance(target[key], dict):
            added += merge_missing(target[key], value, f"{path}{key}.")
    return added


def upgrade_roles(instance: Path, settings: dict[str, Any], reset: bool) -> list[str]:
    """Template roles the instance lacks are added; roles on a provider that no longer exists move to Claude;
    with reset, the pipeline slots take the template's roles (Claude-only defaults)."""
    sys.path.insert(0, str(TEMPLATE / "scripts" / "runner"))
    import providers  # the template's own list of supported providers

    notes = []
    catalog = instance / "catalog" / "agents"
    catalog.mkdir(parents=True, exist_ok=True)
    seeds = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in (TEMPLATE / "templates" / "agents").glob("*.json")}
    for name, seed in seeds.items():
        if not (catalog / f"{name}.json").is_file():
            (catalog / f"{name}.json").write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            notes.append(f"added role {name}")
    for path in sorted(catalog.glob("*.json")):
        role = json.loads(path.read_text(encoding="utf-8"))
        if role.get("provider") not in providers.PROVIDERS:
            replacement = seeds.get(path.stem) or {**role, "provider": "claude", "model": "opus"}
            path.write_text(json.dumps(replacement, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            notes.append(f"role {path.stem}: {role.get('provider')} is no longer supported, now {replacement['provider']} {replacement['model']}")
    seed_pipeline = json.loads((TEMPLATE / "templates" / "research-center.json").read_text(encoding="utf-8"))["pipeline"]
    pipeline = settings.setdefault("pipeline", {})
    for slot, value in seed_pipeline.items():
        current = pipeline.get(slot)
        names = current if isinstance(current, list) else [current]
        broken = current is None or any(not (catalog / f"{name}.json").is_file() for name in names)
        if (reset or broken) and current != value:
            pipeline[slot] = value
            notes.append(f"pipeline.{slot}: {current} -> {value}")
    return notes


def migrate_profiles(instance: Path, settings: dict[str, Any]) -> list[str]:
    """Use cases became profiles (docs/decisions/0015-profiles.md): usecases/<id>/ moves to profiles/<id>/ with git
    history, usecase.json becomes profile.json (the title is the name, the scope's first Who paragraph the
    description), and defaultUseCase becomes defaultProfile. A migrated profile is a company profile, the stricter
    licence rule, until the user changes its type."""
    notes = []
    old_root = instance / "usecases"
    for old in sorted(path.parent for path in old_root.glob("*/usecase.json")):
        new = instance / "profiles" / old.name
        if new.exists():
            notes.append(f"usecases/{old.name} not moved: profiles/{old.name} already exists")
            continue
        new.parent.mkdir(parents=True, exist_ok=True)
        moved = subprocess.run(["git", "-C", str(instance), "mv", f"usecases/{old.name}", f"profiles/{old.name}"], capture_output=True)
        if moved.returncode != 0:
            shutil.move(str(old), str(new))
        meta = json.loads((new / "usecase.json").read_text(encoding="utf-8"))
        description = ""
        if (new / "scope.md").is_file():
            text = (new / "scope.md").read_text(encoding="utf-8")
            who = re.split(r"^## ", text.split("## Who", 1)[1], flags=re.MULTILINE)[0] if "## Who" in text else ""
            description = " ".join(re.sub(r"\s*\[[^\]]*\]", "", who.strip().split("\n\n")[0]).split())[:600]
            (new / "scope.md").write_text(re.sub(r"^Use case: ", "Profile: ", text, count=1, flags=re.MULTILINE),
                                          encoding="utf-8", newline="\n")
        profile = {"schemaVersion": 1, "id": old.name, "name": meta.get("title") or old.name, "description": description,
                   "type": "company", "tags": [], "createdAt": meta.get("createdAt", "")}
        (new / "profile.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        (new / "usecase.json").unlink()
        (new / "inbox").mkdir(exist_ok=True)
        (new / "inbox" / ".gitkeep").touch()
        notes.append(f"use case {old.name} is now profile {old.name} (type company; change it with rc profile edit {old.name} --type personal)")
    if old_root.is_dir() and not any(old_root.iterdir()):
        old_root.rmdir()
    if "defaultUseCase" in settings:
        settings.setdefault("defaultProfile", settings.pop("defaultUseCase"))
        notes.append("setting defaultUseCase is now defaultProfile")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(prog="rc upgrade")
    parser.add_argument("template", type=Path, help="the template root (passed by rc)")
    parser.add_argument("instance", type=Path)
    parser.add_argument("--reset-roles", action="store_true", help="use the template's pipeline roles (Claude-only defaults)")
    parser.add_argument("--force", action="store_true", help="upgrade although the instance has uncommitted changes")
    args = parser.parse_args()
    instance = args.instance.resolve()
    if not (instance / "research-center.json").is_file():
        return fail(f"{instance} is not a Research Center instance (no research-center.json)")
    if instance == TEMPLATE:
        return fail("run rc upgrade from the template (the kit), with the instance's path")
    status = subprocess.run(["git", "-C", str(instance), "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8")
    if status.returncode != 0:
        return fail(f"{instance} is not a git repository; commit it first so the upgrade can be reviewed and reverted")
    if status.stdout.strip() and not args.force:
        return fail(f"{instance} has uncommitted changes; commit them first (or pass --force)")

    for name in MIRRORED_DIRS:
        source, target = TEMPLATE / name, instance / name
        if source.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(source, target, ignore=IGNORED)
    for name in MERGED_DIRS:
        shutil.copytree(TEMPLATE / name, instance / name, ignore=IGNORED, dirs_exist_ok=True)
    for name in FILES:
        if (TEMPLATE / name).is_file():
            (instance / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(TEMPLATE / name, instance / name)
    removed = []
    for name in OBSOLETE:
        path = instance / name
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(name)
        elif path.exists():
            path.unlink()
            removed.append(name)

    settings_path = instance / "research-center.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    seed = json.loads((TEMPLATE / "templates" / "research-center.json").read_text(encoding="utf-8"))
    seed.pop("name", None)
    notes = [f"setting {key} added" for key in merge_missing(settings, {key: value for key, value in seed.items() if key != "pipeline"})]
    notes += upgrade_roles(instance, settings, args.reset_roles)
    notes += migrate_profiles(instance, settings)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for name, source in (("catalog/evidence-types.json", "templates/evidence-types.json"),):
        if not (instance / name).is_file():
            shutil.copy2(TEMPLATE / source, instance / name)
            notes.append(f"added {name}")
    if not (instance / "catalog" / "adapters").is_dir():
        shutil.copytree(TEMPLATE / "templates" / "adapters", instance / "catalog" / "adapters")
        notes.append("added catalog/adapters with the default adapters")

    print(f"upgraded {instance} to the template at {TEMPLATE}")
    for line in notes + [f"removed {name}" for name in removed]:
        print(f"  {line}")
    checks = [subprocess.run([sys.executable, "-B", str(TEMPLATE / "scripts" / script), str(instance)]).returncode
              for script in ("validate-knowledge.py", "validate-research-center.py")]
    print("\nreview the change with git diff in the instance, then commit it; run rc check there")
    return 1 if any(checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
