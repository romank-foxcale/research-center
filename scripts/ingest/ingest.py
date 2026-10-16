#!/usr/bin/env python3
"""./rc ingest: register sources, fetch them into committed text, digest each source (map) and build the
cited profile (reduce). See docs/architecture/research-center.md and docs/decisions/0002-committed-extracted-sources.md.

Sources live in catalog/sources/<id>.json. A run writes sources/<id>/text/..., sources/<id>/manifest.json,
sources/<id>/redactions.md, knowledge/digests/<id>.md and knowledge/profile/*.md. Unchanged sources cost nothing.
"""

from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "runner"))
import extract  # noqa: E402
import rc  # noqa: E402
import secrets_scan  # noqa: E402

KINDS = ("folder", "git", "url", "notion", "gdrive")
CONNECTOR_KINDS = {"notion": "notion", "gdrive": "gdrive"}
ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CITATION = re.compile(r"\[((?:sources|knowledge)/[^\]\s#]+)(?:#[^\]]*)?\]")
PROFILE_KINDS = ("domain", "product", "stack", "problem", "constraint", "decision", "interest", "expertise", "gap", "preference")
DEFAULT_EXCLUDES = ["node_modules/*", "vendor/*", "dist/*", "build/*", "target/*", ".venv/*", "__pycache__/*", "*.lock"]
DOCUMENT = re.compile(r"^=== DOCUMENT: (?P<title>.*?) \| (?P<ref>\S+) ===$", re.MULTILINE)


# Catalog --------------------------------------------------------------------------------------------------


def source_path(root: Path, identifier: str) -> Path:
    return root / "catalog" / "sources" / f"{identifier}.json"


def sources(root: Path) -> list[dict[str, Any]]:
    return [rc.load_json(path) for path in sorted((root / "catalog" / "sources").glob("*.json"))]


def derive_id(kind: str, locator: str) -> str:
    tail = re.split(r"[/\\:]", locator.rstrip("/\\"))[-1] or kind
    tail = re.sub(r"\.git$", "", tail)
    words = re.findall(r"[a-z0-9]+", tail.lower())
    return "-".join([kind, *words])[:60].strip("-")


def command_add(root: Path, args: argparse.Namespace) -> None:
    rc.settings(root)
    identifier = args.id or derive_id(args.kind, args.locators[0])
    if not ID.fullmatch(identifier):
        raise rc.RcError(f"source id must be lowercase hyphen-case: {identifier}")
    if source_path(root, identifier).exists():
        raise rc.RcError(f"source already exists: {identifier}")
    if args.kind in ("folder", "git") and len(args.locators) != 1:
        raise rc.RcError(f"a {args.kind} source has exactly one locator")
    if args.kind == "folder" and not Path(args.locators[0]).expanduser().is_dir():
        raise rc.RcError(f"not a folder: {args.locators[0]}")
    descriptor = {
        "schemaVersion": 1,
        "id": identifier,
        "kind": args.kind,
        "locators": args.locators,
        "include": args.include or [],
        "exclude": args.exclude or [],
        "depth": args.depth,
        "maxDocuments": args.max_documents,
        "note": args.note or "",
        "origin": "user",
        "addedAt": rc.today(),
    }
    rc.write_json(source_path(root, identifier), descriptor)
    print(f"added source {identifier} ({args.kind}); fetch it with ./rc ingest run {identifier}")


def command_remove(root: Path, args: argparse.Namespace) -> None:
    path = source_path(root, args.id)
    if not path.exists():
        raise rc.RcError(f"no such source: {args.id}")
    path.unlink()
    shutil.rmtree(root / "sources" / args.id, ignore_errors=True)
    (root / "knowledge" / "digests" / f"{args.id}.md").unlink(missing_ok=True)
    print(f"removed source {args.id}, its text and digest; rebuild the profile with ./rc ingest run --profile")


def command_list(root: Path, _: argparse.Namespace) -> None:
    for descriptor in sources(root):
        manifest = read_manifest(root, descriptor["id"])
        files = len(manifest.get("files", {}))
        fetched = manifest.get("fetchedAt", "never")
        digest = "fresh" if digest_fresh(root, descriptor["id"], manifest) else "stale"
        print(f"{descriptor['id']:<36} {descriptor['kind']:<7} files {files:<5} fetched {fetched:<20} digest {digest}  {' '.join(descriptor['locators'])}")


# Guard ----------------------------------------------------------------------------------------------------


def github_slug(remote: str) -> str | None:
    match = re.match(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$", remote)
    return match.group(1) if match else None


def visibility(slug: str) -> str | None:
    try:
        result = subprocess.run(["gh", "repo", "view", slug, "--json", "visibility", "--jq", ".visibility"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip().upper() if result.returncode == 0 else None


def guard(root: Path, lookup=visibility) -> None:
    """Refuse to commit sources into the template or into a repo that is, or may be, public."""
    config = rc.settings(root)
    result = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    remote = result.stdout.strip() if result.returncode == 0 else ""
    if not remote:
        return  # nothing is published from a repo without a remote
    slug = github_slug(remote)
    if slug:
        seen = lookup(slug)
        if seen in ("PRIVATE", "INTERNAL"):
            return
        raise rc.RcError(f"origin {slug} is {seen or 'of unknown visibility (gh failed)'}: ingest commits source text, "
                         "so the instance repo must be private")
    if config.get("privateRemoteConfirmed") is True:
        return
    raise rc.RcError(f"origin {remote} is not on GitHub, so its visibility cannot be checked; set "
                     f"\"privateRemoteConfirmed\": true in {rc.SETTINGS} once you have made sure it is private")


# Fetching -------------------------------------------------------------------------------------------------


def matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(Path(name).name, pattern) for pattern in patterns)


def selected(name: str, descriptor: dict[str, Any]) -> bool:
    if descriptor.get("include") and not matches(name, descriptor["include"]):
        return False
    return not matches(name, DEFAULT_EXCLUDES + descriptor.get("exclude", []))


def folder_files(folder: Path) -> list[str]:
    names = []
    for directory, subdirectories, files in os.walk(folder):
        subdirectories[:] = sorted(entry for entry in subdirectories if not entry.startswith("."))
        for file in sorted(files):
            if not file.startswith("."):
                names.append((Path(directory) / file).relative_to(folder).as_posix())
    return names


def git_remote(checkout: Path, locator: str) -> str:
    """The repo's portable name for handoffs: its origin URL, else the locator when that is a URL."""
    result = subprocess.run(["git", "-C", str(checkout), "remote", "get-url", "origin"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return locator if "://" in locator or locator.startswith("git@") else ""


def git_checkout(root: Path, descriptor: dict[str, Any]) -> tuple[Path, str]:
    """A local repo is read in place; a remote one is cloned (shallow) into the ignored cache."""
    locator = descriptor["locators"][0]
    local = Path(locator).expanduser()
    if local.is_dir():
        checkout = local
    else:
        checkout = root / ".rc-local" / "cache" / "git" / descriptor["id"]
        if (checkout / ".git").is_dir():
            subprocess.run(["git", "-C", str(checkout), "fetch", "--depth", "1", "origin", "HEAD"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(checkout), "reset", "--hard", "FETCH_HEAD"], check=True, capture_output=True)
        else:
            checkout.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--depth", "1", "--", locator, str(checkout)], check=True, capture_output=True)
    revision = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
    return checkout, revision


def git_files(checkout: Path) -> list[str]:
    listed = subprocess.run(["git", "-C", str(checkout), "ls-files", "-z"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return sorted(name for name in listed.stdout.split("\0") if name)


def url_slug(url: str) -> str:
    words = re.findall(r"[a-z0-9]+", re.sub(r"^https?://(www\.)?", "", url.lower()))
    return "-".join(words)[:70].strip("-") + "-" + hashlib.sha256(url.encode()).hexdigest()[:6]


def fetch_url(url: str, limit: int = 15 * 1024 * 1024) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "research-center/1 (+https://github.com/romank-foxcale/research-center)"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(limit + 1)
        kind = response.headers.get_content_type()
    if len(data) > limit:
        raise extract.Skip(f"larger than {limit} bytes")
    return data, kind


def url_document(url: str) -> tuple[str, str, str, bytes]:
    """(stored name, text, extractor, original bytes) of one URL."""
    data, kind = fetch_url(url)
    if kind == "application/pdf" or url.lower().endswith(".pdf"):
        text, _, extractor = extract.extract("page.pdf", data)
    elif kind in ("text/html", "application/xhtml+xml"):
        text, extractor = extract.html_to_markdown(data), "markdownify"
    elif kind.startswith("text/") or kind in ("application/json", "application/xml"):
        text, extractor = extract.decode(data), "text"
    else:
        raise extract.Skip(f"unsupported content type {kind}")
    return f"{url_slug(url)}.md", f"Source: {url}\n\n{text}", extractor, data


def connector_documents(session: rc.Session, root: Path, descriptor: dict[str, Any]) -> list[tuple[str, str]]:
    """(reference, Markdown) of each Notion page or Drive document, read by the connector role."""
    config = rc.settings(root)
    role_id = config["pipeline"]["connectorReader"]
    body = (
        f"# Task\n\nRead from {descriptor['kind']}: {json.dumps(descriptor['locators'])}.\n"
        f"Follow child pages or folder contents to depth {descriptor.get('depth', 1)}, at most "
        f"{descriptor.get('maxDocuments', 20)} documents. A locator starting with 'search:' is a search query.\n"
        "Reproduce each document's content verbatim as Markdown, each one starting with a line\n"
        "`=== DOCUMENT: <title> | <url or id> ===`."
    )

    def check(reply: str) -> list[tuple[str, str]]:
        parts = DOCUMENT.split(reply)
        documents = []
        for index in range(1, len(parts) - 2, 3):
            title, reference, content = parts[index], parts[index + 1], parts[index + 2].strip()
            if content:
                documents.append((reference, f"# {title}\n\nSource: {reference}\n\n{content}"))
        if not documents:
            raise ValueError("no `=== DOCUMENT: <title> | <url or id> ===` sections with content")
        return documents

    return session.call_checked(role_id, body, f"connector-{descriptor['id']}", check)


def collect(session: rc.Session | None, root: Path, descriptor: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[dict[str, str]], dict[str, str]]:
    """Fetch one source: ({stored: entry}, {stored: text}, skipped, git revision and remote)."""
    config = rc.settings(root)["ingest"]
    max_file, max_source = config["maxFileBytes"], config["maxSourceBytes"]
    entries: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    skipped: list[dict[str, str]] = []
    revision: dict[str, str] = {}
    total = 0

    def keep(origin: str, stored: str, text: str, extractor: str, original: bytes) -> None:
        nonlocal total
        size = len(text.encode("utf-8"))
        if size > max_file:
            skipped.append({"origin": origin, "reason": f"text is {size} bytes, over maxFileBytes {max_file}"})
            return
        total += size
        if total > max_source:
            raise rc.RcError(f"source {descriptor['id']} exceeds maxSourceBytes {max_source}; narrow it with --include/--exclude "
                             f"or raise ingest.maxSourceBytes in {rc.SETTINGS}")
        texts[stored] = text
        entries[stored] = {"origin": origin, "sha256": hashlib.sha256(original).hexdigest(), "extractor": extractor}

    kind = descriptor["kind"]
    if kind in ("folder", "git"):
        if kind == "folder":
            base = Path(descriptor["locators"][0]).expanduser()
            names = folder_files(base)
        else:
            base, sha = git_checkout(root, descriptor)
            revision = {"revision": sha, "remote": git_remote(base, descriptor["locators"][0])}
            names = git_files(base)
        for name in names:
            if not selected(name, descriptor):
                continue
            path = base / name
            if not path.is_file() or path.is_symlink():
                continue
            data = path.read_bytes()
            try:
                text, stored, extractor = extract.extract(name, data)
            except extract.Skip as reason:
                skipped.append({"origin": name, "reason": str(reason)})
                continue
            keep(name, stored, text, extractor, data)
    elif kind == "url":
        for url in descriptor["locators"]:
            try:
                stored, text, extractor, data = url_document(url)
            except (extract.Skip, urllib.error.URLError, OSError, ValueError) as reason:
                skipped.append({"origin": url, "reason": str(reason)[:200]})
                continue
            keep(url, stored, text, extractor, data)
    elif kind in CONNECTOR_KINDS:
        if session is None:
            raise rc.RcError(f"{kind} sources need an agent session")
        for reference, text in connector_documents(session, root, descriptor):
            keep(reference, f"{url_slug(reference)}.md", text, f"connector-{kind}", text.encode("utf-8"))
    else:
        raise rc.RcError(f"unknown source kind {kind}")
    return entries, texts, skipped, revision


def read_manifest(root: Path, identifier: str) -> dict[str, Any]:
    path = root / "sources" / identifier / "manifest.json"
    return rc.load_json(path) if path.is_file() else {}


def fingerprint(manifest: dict[str, Any]) -> str:
    files = manifest.get("files", {})
    return hashlib.sha256(json.dumps(sorted((name, entry["sha256"]) for name, entry in files.items())).encode()).hexdigest()[:16]


def store(root: Path, descriptor: dict[str, Any], entries: dict[str, dict[str, Any]], texts: dict[str, str],
          skipped: list[dict[str, str]], revision: dict[str, str]) -> tuple[int, int]:
    """Write a fetched source: redacted text, manifest, redaction report. Returns (changed files, redactions).
    revision: a git source's {"revision": sha, "remote": url}; empty for other kinds."""
    directory = root / "sources" / descriptor["id"]
    previous = read_manifest(root, descriptor["id"]).get("files", {})
    text_root = directory / "text"
    redactions: list[str] = []
    changed = 0
    for stored, text in sorted(texts.items()):
        clean, found = secrets_scan.redact(text)
        target = text_root / stored
        if previous.get(stored, {}).get("sha256") != entries[stored]["sha256"] or not target.is_file():
            changed += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(clean, encoding="utf-8", newline="\n")
        redactions += [f"| {stored} | {item['line']} | {item['kind']} |" for item in found]
        entries[stored]["redactions"] = len(found)
    for stale in set(previous) - set(entries):
        (text_root / stale).unlink(missing_ok=True)
        changed += 1
    if text_root.is_dir():
        for directory_path in sorted(text_root.rglob("*"), reverse=True):
            if directory_path.is_dir() and not any(directory_path.iterdir()):
                directory_path.rmdir()
    manifest = {
        "schemaVersion": 1,
        "id": descriptor["id"],
        "kind": descriptor["kind"],
        "locators": descriptor["locators"],
        "revision": revision.get("revision", ""),
        "remote": revision.get("remote", ""),
        "fetchedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": dict(sorted(entries.items())),
        "skipped": skipped,
    }
    rc.write_json(directory / "manifest.json", manifest)
    report = directory / "redactions.md"
    if redactions:
        report.write_text(
            f"# Redactions in {descriptor['id']}\n\nValues were replaced with [REDACTED:<kind>] before commit. "
            "Rotate any real credential listed here: it existed in the original.\n\n| File | Line | Kind |\n| --- | --- | --- |\n"
            + "\n".join(redactions) + "\n", encoding="utf-8", newline="\n")
    else:
        report.unlink(missing_ok=True)
    return changed, len(redactions)


# Digest (map) and profile (reduce) ---------------------------------------------------------------------------


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        return {}
    return dict(re.findall(r"^([a-z_]+):\s*(.+)$", match.group(1), flags=re.MULTILINE))


def digest_fresh(root: Path, identifier: str, manifest: dict[str, Any]) -> bool:
    path = root / "knowledge" / "digests" / f"{identifier}.md"
    return bool(manifest) and path.is_file() and frontmatter(path.read_text(encoding="utf-8")).get("fingerprint") == fingerprint(manifest)


def chunks(root: Path, identifier: str, manifest: dict[str, Any], size: int) -> list[list[str]]:
    groups: list[list[str]] = [[]]
    used = 0
    for stored in manifest["files"]:
        path = f"sources/{identifier}/text/{stored}"
        length = (root / path).stat().st_size
        if groups[-1] and used + length > size:
            groups.append([])
            used = 0
        groups[-1].append(path)
        used += length
    return [group for group in groups if group]


def checked_citations(root: Path, markdown: str) -> tuple[str, int]:
    """Drop every fact line whose citations are missing or point nowhere; (kept Markdown, dropped lines).
    A nested bullet without citations of its own inherits its kept parent's ("three milestones:" + M1..M3)."""
    kept, dropped = [], 0
    parent_kept = False
    for line in markdown.splitlines():
        if line.lstrip().startswith(("- ", "* ")):
            nested = line[0] in " \t"
            cited = CITATION.findall(line)
            broken = any(not (root / path).is_file() for path in cited)
            if broken or (not cited and not (nested and parent_kept)):
                dropped += 1
                parent_kept = parent_kept if nested else False
                continue
            parent_kept = parent_kept if nested else True
        kept.append(line)
    return "\n".join(kept).strip(), dropped


def digest(session: rc.Session, root: Path, descriptor: dict[str, Any], manifest: dict[str, Any]) -> None:
    config = rc.settings(root)
    role_id = config["pipeline"]["digester"]
    groups = chunks(root, descriptor["id"], manifest, config["ingest"]["chunkBytes"])
    parts, dropped_total = [], 0
    for number, group in enumerate(groups, 1):
        body = (
            f"# Task\n\nDigest part {number} of {len(groups)} of source `{descriptor['id']}` ({descriptor['kind']}: "
            f"{', '.join(descriptor['locators'])}). {descriptor.get('note', '')}\n\nRead these files:\n\n"
            + "\n".join(f"- {path}" for path in group)
        )

        def check(reply: str) -> tuple[str, int]:
            kept, dropped = checked_citations(root, re.sub(r"\A---\n.*?\n---\n", "", reply.strip(), flags=re.DOTALL))
            if "## Key facts" not in kept or not CITATION.search(kept):
                raise ValueError("the digest needs a '## Key facts' section whose bullets cite [sources/...] paths that exist")
            return kept, dropped

        kept, dropped = session.call_checked(role_id, body, f"digest-{descriptor['id']}-{number}", check)
        dropped_total += dropped
        parts.append(kept if len(groups) == 1 else f"# Part {number}\n\n{kept}")
    summary = next((line.strip() for text in parts for line in text.splitlines()
                    if line.strip() and not line.startswith(("#", "-", "*", "|"))), descriptor["id"])
    header = (
        f"---\nid: digest.{descriptor['id']}\ntitle: Digest of {descriptor['id']}\nstatus: active\n"
        f"summary: {summary[:300]}\nverified_at: {rc.today()}\nfingerprint: {fingerprint(manifest)}\n"
        f"evidence:\n  - sources/{descriptor['id']}/manifest.json\nrelations:\n  - catalog/sources/{descriptor['id']}.json\n---\n\n"
    )
    rc.write_text(root / "knowledge" / "digests" / f"{descriptor['id']}.md", header + "\n\n".join(parts))
    if dropped_total:
        session.say(f"digest {descriptor['id']}: dropped {dropped_total} uncited or mis-cited fact lines", "warn")


def profile(session: rc.Session, root: Path) -> None:
    config = rc.settings(root)
    digests = sorted((root / "knowledge" / "digests").glob("*.md"))
    if not digests:
        raise rc.RcError("no digests to build a profile from")
    body = (
        "# Task\n\nBuild the profile from these digests (read each one, and the cited source files where a digest is unclear):\n\n"
        + "\n".join(f"- {path.relative_to(root).as_posix()}" for path in digests)
        + f"\n\nAllowed kinds: {', '.join(PROFILE_KINDS)}."
    )

    def check(reply: str) -> dict[str, Any]:
        data = rc.extract_json(reply)
        notes = data.get("notes") if isinstance(data, dict) else None
        if not notes:
            raise ValueError("expected JSON {\"summary\": ..., \"notes\": [...]} with at least one note")
        problems, slugs = [], set()
        for note in notes:
            slug = note.get("slug", "")
            if not ID.fullmatch(slug) or slug in slugs or slug == "index":
                problems.append(f"note slug {slug!r} must be unique lowercase hyphen-case")
            slugs.add(slug)
            if note.get("kind") not in PROFILE_KINDS:
                problems.append(f"{slug}: kind {note.get('kind')!r} is not one of {PROFILE_KINDS}")
            for field in ("title", "summary", "body"):
                if not str(note.get(field, "")).strip():
                    problems.append(f"{slug}: {field} is empty")
            evidence = note.get("evidence") or []
            if not evidence:
                problems.append(f"{slug}: evidence is empty")
            for path in evidence + CITATION.findall(str(note.get("body", ""))):
                if not path.startswith("sources/") or not (root / path).is_file():
                    problems.append(f"{slug}: evidence {path} is not an existing file under sources/")
        if problems:
            raise ValueError("; ".join(problems[:30]))
        return data

    data = session.call_checked(config["pipeline"]["profiler"], body, "profile", check)
    directory = root / "knowledge" / "profile"
    if directory.is_dir():
        shutil.rmtree(directory)  # the profile is rebuilt whole; history is in Git
    one_line = lambda value: " ".join(str(value).split())  # noqa: E731
    for note in data["notes"]:
        evidence = "".join(f"  - {path}\n" for path in dict.fromkeys(note["evidence"]))
        rc.write_text(directory / f"{note['slug']}.md", (
            f"---\nid: profile.{note['slug']}\ntitle: {one_line(note['title'])}\nstatus: active\nkind: {note['kind']}\n"
            f"summary: {one_line(note['summary'])}\nverified_at: {rc.today()}\nevidence:\n{evidence}"
            f"relations:\n  - knowledge/profile/index.md\n---\n\n# {one_line(note['title'])}\n\n{note['body'].strip()}\n"
        ))
    lines = []
    for kind in PROFILE_KINDS:
        members = [note for note in data["notes"] if note["kind"] == kind]
        if members:
            lines.append(f"\n## {kind.capitalize()}\n")
            lines += [f"- [{one_line(note['title'])}]({note['slug']}.md): {one_line(note['summary'])}" for note in members]
    digest_list = "".join(f"  - {path.relative_to(root).as_posix()}\n" for path in digests)
    rc.write_text(directory / "index.md", (
        f"---\nid: profile.index\ntitle: Profile\nstatus: active\nsummary: {one_line(data.get('summary', 'What the ingested sources say about the user or company.'))}\n"
        f"verified_at: {rc.today()}\nevidence:\n{digest_list}relations:\n  - research-center.json\n---\n\n"
        f"# Profile\n\n{data.get('summary', '').strip()}\n" + "\n".join(lines) + "\n"
    ))
    session.say(f"profile: {len(data['notes'])} notes in knowledge/profile")


# Run ------------------------------------------------------------------------------------------------------


def run_ingest(root: Path, wanted: list[str], budget: int | None, profile_mode: str, guard_lookup=visibility) -> int:
    config = rc.settings(root)
    guard(root, guard_lookup)
    known = {descriptor["id"]: descriptor for descriptor in sources(root) if descriptor.get("origin", "user") == "user"}
    unknown = [identifier for identifier in wanted if identifier not in known]
    if unknown:
        raise rc.RcError(f"unknown sources: {', '.join(unknown)} (see ./rc ingest list)")
    chosen = [known[identifier] for identifier in (wanted or sorted(known))]
    if not chosen and profile_mode != "only":
        print("no sources yet: add one with ./rc ingest add <folder|git|url|notion|gdrive> <locator>")
        return 0
    with rc.Session(root, "ingest", budget or config["budget"]["ingestCalls"]) as session:
        stale = False
        if profile_mode != "only":
            for descriptor in chosen:
                session.say(f"fetch {descriptor['id']} ({descriptor['kind']})")
                entries, texts, skipped, revision = collect(session, root, descriptor)
                changed, redacted = store(root, descriptor, entries, texts, skipped, revision)
                session.say(f"fetch {descriptor['id']}: {len(entries)} files, {changed} changed, {len(skipped)} skipped, {redacted} redactions")
                if redacted:
                    session.say(f"{descriptor['id']}: {redacted} secrets redacted; see sources/{descriptor['id']}/redactions.md", "warn")
                manifest = read_manifest(root, descriptor["id"])
                if not manifest.get("files"):
                    session.say(f"{descriptor['id']}: nothing to digest", "warn")
                    continue
                if digest_fresh(root, descriptor["id"], manifest):
                    continue
                session.say(f"digest {descriptor['id']}")
                digest(session, root, descriptor, manifest)
                stale = True
        profile_missing = not (root / "knowledge" / "profile" / "index.md").is_file()
        if profile_mode == "only" or (profile_mode == "auto" and (stale or profile_missing)):
            session.say("profile: reduce every digest into cited notes")
            profile(session, root)
        session.say(f"ingest finished with {session.calls} agent calls; review, then commit sources/ and knowledge/", "gate")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="./rc ingest")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="register a source")
    add.add_argument("kind", choices=KINDS)
    add.add_argument("locators", nargs="+", help="folder path, repo URL or path, URLs, Notion/Drive URLs or 'search:<query>'")
    add.add_argument("--id")
    add.add_argument("--include", action="append", help="glob of files to keep (folder, git); repeatable")
    add.add_argument("--exclude", action="append", help="glob of files to drop (folder, git); repeatable")
    add.add_argument("--depth", type=int, default=1, help="child pages/folders to follow (notion, gdrive)")
    add.add_argument("--max-documents", type=int, default=20)
    add.add_argument("--note", help="what this source is and why it matters")
    remove = commands.add_parser("remove")
    remove.add_argument("id")
    commands.add_parser("list")
    run = commands.add_parser("run", help="fetch, digest and profile")
    run.add_argument("ids", nargs="*")
    run.add_argument("--budget", type=int)
    run.add_argument("--profile", dest="profile_mode", action="store_const", const="only", default="auto",
                     help="only rebuild the profile from the existing digests")
    run.add_argument("--no-profile", dest="profile_mode", action="store_const", const="never")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "add":
            command_add(root, args)
        elif args.command == "remove":
            command_remove(root, args)
        elif args.command == "list":
            command_list(root, args)
        else:
            return run_ingest(root, args.ids, args.budget, args.profile_mode)
    except (rc.RcError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
