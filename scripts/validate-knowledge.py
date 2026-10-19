#!/usr/bin/env python3
"""Validate the repository's small, linked Markdown knowledge graph."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from rule_hooks import extra_markdown_dirs, markdown_allowed

REQUIRED_FILES = ("README.md", "AGENTS.md", "rc.py", "pyproject.toml", "docs/index.md")
REQUIRED_FIELDS = ("id", "title", "status", "summary", "verified_at")
ALLOWED_STATUSES = {"active", "accepted", "draft", "superseded", "archived"}
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_frontmatter(path: Path, text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("unclosed YAML frontmatter") from error

    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    current_list: str | None = None
    for line in lines[1:end]:
        field = re.match(r"^([a-z_]+):(?:\s*(.*))?$", line)
        if field:
            name, value = field.group(1), (field.group(2) or "").strip().strip('"')
            current_list = name if not value else None
            if value:
                scalars[name] = value
            else:
                lists[name] = []
            continue
        item = re.match(r"^\s+-\s+(.+?)\s*$", line)
        if item and current_list:
            lists[current_list].append(item.group(1).strip().strip('"'))
    return scalars, lists


def local_target(root: Path, note: Path, raw: str, from_root: bool) -> Path | None:
    target = raw.split("#", 1)[0].strip().strip("<>")
    if not target or target.startswith(("http://", "https://", "mailto:")):
        return None
    base = root if from_root else note.parent
    return (base / target).resolve()


def repository_files(root: Path) -> list[str]:
    """Files Git would commit: tracked and untracked, never ignored. A Nix source copy has no .git
    and holds only tracked files, so a plain walk is exact there."""
    if (root / ".git").exists():
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if listed.returncode == 0:
            return listed.stdout.splitlines()
    return [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()]


def stray_markdown(root: Path) -> list[str]:
    extra = extra_markdown_dirs(root)
    return [
        f"{name}: Markdown outside docs/, plans/, the skills and research-center.json markdownDirs; "
        "store it as a note under docs/"
        for name in repository_files(root)
        if name.lower().endswith(".md") and not markdown_allowed(name, extra)
    ]


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()

    for name in REQUIRED_FILES:
        if not (root / name).exists():
            errors.append(f"{name}: required file is missing")

    notes = sorted((root / "docs").rglob("*.md")) if (root / "docs").exists() else []
    identifiers: dict[str, Path] = {}

    for note in notes:
        relative = note.relative_to(root)
        text = note.read_text(encoding="utf-8")
        try:
            scalars, lists = parse_frontmatter(note, text)
        except ValueError as error:
            errors.append(f"{relative}: {error}")
            continue

        if len(text.splitlines()) > 220 and scalars.get("kind", "note") != "research-reference":
            errors.append(f"{relative}: note exceeds 220 lines; split it")

        for field in REQUIRED_FIELDS:
            if not scalars.get(field):
                errors.append(f"{relative}: missing frontmatter field '{field}'")

        identifier = scalars.get("id")
        if identifier:
            if identifier in identifiers:
                errors.append(
                    f"{relative}: duplicate id '{identifier}' also used by {identifiers[identifier].relative_to(root)}"
                )
            identifiers[identifier] = note

        status = scalars.get("status")
        if status and status not in ALLOWED_STATUSES:
            errors.append(f"{relative}: unsupported status '{status}'")

        verified_at = scalars.get("verified_at")
        if verified_at and not DATE.fullmatch(verified_at):
            errors.append(f"{relative}: verified_at must use YYYY-MM-DD")

        for field in ("evidence", "relations"):
            values = lists.get(field, [])
            if not values:
                errors.append(f"{relative}: '{field}' must contain at least one path")
            for value in values:
                target = local_target(root, note, value, from_root=True)
                if target and not target.exists():
                    errors.append(f"{relative}: broken {field} path '{value}'")
                # docs/ is copied into every instance, the template's own plans are not: such a link breaks there.
                if value.startswith("plans/") and not (root / "research-center.json").is_file():
                    errors.append(
                        f"{relative}: {field} path '{value}' points at a template plan, which instances do not get"
                    )

        for raw_link in MARKDOWN_LINK.findall(text):
            target = local_target(root, note, raw_link, from_root=False)
            if target and not target.exists():
                errors.append(f"{relative}: broken Markdown link '{raw_link}'")

    if not notes:
        errors.append("docs/: no Markdown notes found")
    errors.extend(stray_markdown(root))
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    errors = validate(root)
    if errors:
        print("knowledge validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    count = len(list((root / "docs").rglob("*.md")))
    print(f"knowledge validation passed: {count} notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
