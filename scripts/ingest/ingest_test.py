#!/usr/bin/env python3
"""Test ingest end to end with a fake provider: a folder becomes redacted committed text, a digest that keeps
only cited facts and a cited profile; unchanged sources cost no calls; the guard refuses public remotes; the
budget stops a run without losing finished work."""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent / "runner")]
import extract  # noqa: E402
import ingest  # noqa: E402
import providers  # noqa: E402

import rc  # noqa: E402

SECRET = "Hunter2-xyz!9"
CALLS: list[str] = []


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_rc", REPO / "scripts" / "validate-research-center.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_instance(base: Path) -> Path:
    """A minimal instance: settings and roles from the template, the skills, the templates."""
    root = base / "rc"
    (root / "catalog").mkdir(parents=True)
    shutil.copytree(REPO / "templates" / "agents", root / "catalog" / "agents")
    shutil.copytree(REPO / ".agents", root / ".agents")
    shutil.copytree(REPO / "templates", root / "templates")
    settings = json.loads((REPO / "templates" / "research-center.json").read_text())
    settings["name"] = "test"
    (root / "research-center.json").write_text(json.dumps(settings))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def fake_run(role, prompt, cwd, log, timeout=0, on_say=None, shared=None):
    CALLS.append(role["id"])
    if role["id"] == "digester":
        paths = [line[2:] for line in prompt.splitlines() if line.startswith("- sources/")]
        return (
            "A small product repo with a Python service.\n\n## Key facts\n\n"
            f"- The service is written in Python. [{paths[0]}]\n"
            "  - It targets Python 3.13.\n"
            "- An uncited claim that must be dropped.\n"
            "  - Its uncited child goes with it.\n"
            "- A claim citing a file that does not exist. [sources/nowhere/text/x.md]\n"
        )
    if role["id"] == "profiler":
        digest = next(line[2:] for line in prompt.splitlines() if line.startswith("- knowledge/digests/"))
        source = digest.removeprefix("knowledge/digests/").removesuffix(".md")
        evidence = f"sources/{source}/text/README.md"
        return (
            "Here is the profile.\n\n```json\n"
            + json.dumps(
                {
                    "summary": "A team building a Python service.",
                    "notes": [
                        {
                            "slug": "python-service",
                            "kind": "stack",
                            "title": "Python service",
                            "summary": "The product is Python.",
                            "body": f"Written in Python [{evidence}].",
                            "evidence": [evidence],
                        }
                    ],
                }
            )
            + "\n```"
        )
    raise AssertionError(f"unexpected role {role['id']}")


def quiet(function, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


def check_extract() -> None:
    text, stored, extractor = extract.extract("docs/My Notes.md", b"# Notes\n")
    assert (stored, extractor) == ("docs/My_Notes.md", "text"), stored
    assert extract.extract("src/app.py", b"print(1)\n")[1] == "src/app.py.txt", "code gets a .txt suffix"
    assert extract.extract("flake.nix", b"{}")[1] == "flake.nix.txt", "no ingested file can be a flake"
    for name, data in (("logo.png", b"\x89PNG\0\0"), ("package-lock.json", b"{}"), ("data.bin", b"\0\0")):
        try:
            extract.extract(name, data)
            raise AssertionError(f"{name} must be skipped")
        except extract.Skip:
            pass
    html = b"<html><body><h1>Title</h1><p>Hello <b>world</b></p><script>evil()</script></body></html>"
    text, stored, extractor = extract.extract("page.html", html)
    assert "# Title" in text and "world" in text and "evil" not in text and stored == "page.html.md", text
    try:
        from openpyxl import Workbook

        book = Workbook()
        book.active.append(["name", "score"])
        book.active.append(["a", 1])
        buffer = io.BytesIO()
        book.save(buffer)
        text, stored, _ = extract.extract("sheet.xlsx", buffer.getvalue())
        assert "name | score" in text and stored == "sheet.xlsx.md", text
    except ImportError:
        print("note: openpyxl missing; xlsx extraction not tested outside the Nix check")


def check_git_remote(base: Path) -> None:
    repo = base / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert ingest.git_remote(repo, str(repo)) == "", "a local path is never a portable name"
    assert ingest.git_remote(repo, "https://github.com/acme/api") == "https://github.com/acme/api"
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:acme/api.git"], check=True)
    assert ingest.git_remote(repo, str(repo)) == "git@github.com:acme/api.git"


def check_guard(base: Path) -> None:
    root = make_instance(base / "guard")
    ingest.guard(root, lambda slug: None)  # no remote: nothing is published
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://github.com/acme/rc.git"], check=True)
    for seen in ("PUBLIC", None):
        try:
            ingest.guard(root, lambda slug, seen=seen: seen)
            raise AssertionError(f"visibility {seen} must be refused")
        except rc.RcError as error:
            assert "private" in str(error)
    ingest.guard(root, lambda slug: "PRIVATE" if slug == "acme/rc" else None)
    subprocess.run(
        ["git", "-C", str(root), "remote", "set-url", "origin", "https://gitlab.example.com/acme/rc.git"], check=True
    )
    try:
        ingest.guard(root, lambda slug: "PRIVATE")
        raise AssertionError("an unverifiable remote must be refused")
    except rc.RcError as error:
        assert "privateRemoteConfirmed" in str(error)
    settings = json.loads((root / "research-center.json").read_text())
    (root / "research-center.json").write_text(json.dumps({**settings, "privateRemoteConfirmed": True}))
    ingest.guard(root, lambda slug: None)
    template = base / "template"
    template.mkdir()
    try:
        ingest.guard(template)
        raise AssertionError("the template must refuse")
    except rc.RcError as error:
        assert "template" in str(error)


def check_folder_ingest(base: Path) -> None:
    root = make_instance(base / "ingest")
    corpus = base / "corpus"
    (corpus / "src").mkdir(parents=True)
    (corpus / "README.md").write_text("# Service\n\nA Python service.\n")
    (corpus / "src" / "app.py").write_text("print('hello')\n")
    (corpus / "config.yaml").write_text(f'password: "{SECRET}"\n')
    (corpus / "logo.png").write_bytes(b"\x89PNG\0\0\0")
    (corpus / ".hidden").write_text("skip me\n")
    (corpus / "node_modules").mkdir()
    (corpus / "node_modules" / "x.js").write_text("x\n")

    args = argparse.Namespace(
        kind="folder",
        locators=[str(corpus)],
        id="corpus",
        include=None,
        exclude=None,
        depth=1,
        max_documents=20,
        note="test corpus",
    )
    quiet(ingest.command_add, root, args)
    quiet(ingest.run_ingest, root, [], None, "auto", lambda slug: None)
    text_root = root / "sources" / "corpus" / "text"
    stored = sorted(path.relative_to(text_root).as_posix() for path in text_root.rglob("*") if path.is_file())
    assert stored == ["README.md", "config.yaml.txt", "src/app.py.txt"], stored
    assert (
        SECRET not in (text_root / "config.yaml.txt").read_text()
        and "[REDACTED:assigned-secret]" in (text_root / "config.yaml.txt").read_text()
    )
    report = (root / "sources" / "corpus" / "redactions.md").read_text()
    assert "config.yaml.txt | 1 | assigned-secret" in report and SECRET not in report, report
    manifest = json.loads((root / "sources" / "corpus" / "manifest.json").read_text())
    assert {item["origin"] for item in manifest["skipped"]} == {"logo.png"}, manifest["skipped"]

    digest = (root / "knowledge" / "digests" / "corpus.md").read_text()
    assert "uncited" not in digest and "does not exist" not in digest and "written in Python" in digest, digest
    assert "  - It targets Python 3.13." in digest, "a nested bullet inherits its parent's citation"
    assert f"fingerprint: {ingest.fingerprint(manifest)}" in digest
    note = (root / "knowledge" / "profile" / "python-service.md").read_text()
    assert "kind: stack" in note and "  - sources/corpus/text/README.md" in note, note
    assert "[Python service](python-service.md)" in (root / "knowledge" / "profile" / "index.md").read_text()
    assert CALLS == ["digester", "profiler"], CALLS
    assert load_validator().validate(root) == [], load_validator().validate(root)

    CALLS.clear()
    quiet(ingest.run_ingest, root, [], None, "auto", lambda slug: None)
    assert CALLS == [], f"an unchanged source costs no agent call: {CALLS}"

    (corpus / "src" / "app.py").write_text("print('changed')\n")
    (corpus / "config.yaml").unlink()
    quiet(ingest.run_ingest, root, [], None, "auto", lambda slug: None)
    assert CALLS == ["digester", "profiler"], CALLS
    assert (
        not (text_root / "config.yaml.txt").exists() and not (root / "sources" / "corpus" / "redactions.md").exists()
    ), "a file gone from the origin leaves the committed text, and its redaction report goes with it"

    # Budget: two sources need two digests; a budget of one keeps the first and stops.
    CALLS.clear()
    (corpus / "README.md").write_text("# Service\n\nChanged.\n")
    second = base / "second"
    second.mkdir()
    (second / "notes.md").write_text("# Notes\n\nMore.\n")
    quiet(ingest.command_add, root, argparse.Namespace(**{**vars(args), "locators": [str(second)], "id": "second"}))
    try:
        quiet(ingest.run_ingest, root, [], 1, "auto", lambda slug: None)
        raise AssertionError("the budget must stop the run")
    except rc.BudgetExceeded:
        pass
    assert CALLS == ["digester"] and ingest.digest_fresh(root, "corpus", ingest.read_manifest(root, "corpus")), (
        "the finished digest is kept"
    )
    assert (root / "sources" / "second" / "manifest.json").is_file() and not (
        root / "knowledge" / "digests" / "second.md"
    ).exists()

    # The template refuses to hold data.
    template = base / "template"
    shutil.copytree(REPO / "templates", template / "templates")
    shutil.copytree(REPO / ".agents", template / ".agents")
    assert load_validator().validate(template) == []
    (template / "sources" / "x").mkdir(parents=True)
    (template / "sources" / "x" / "a.md").write_text("data\n")
    assert any("ships no data" in error for error in load_validator().validate(template))


def test_ingest(monkeypatch) -> None:
    monkeypatch.setattr(providers, "run", fake_run)
    check_extract()
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        check_git_remote(base)
        check_guard(base)
        check_folder_ingest(base)
