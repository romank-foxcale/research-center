#!/usr/bin/env python3
"""Test rc upgrade on a simulated old instance: template-owned files are replaced and Nix files removed, instance
data is untouched, missing settings and roles are added without overwriting, a Cursor role moves to Claude,
--reset-roles takes the template's pipeline, and an instance with uncommitted changes is refused."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = HERE / "upgrade-instance.py"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def upgrade(instance: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPT), str(REPO), str(instance), *flags], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def old_instance(base: Path) -> Path:
    root = base / "old_RC"
    (root / "catalog" / "agents").mkdir(parents=True)
    for path in (REPO / "templates" / "agents").glob("*.json"):
        if path.stem not in ("screener", "researcher-sonnet", "sceptic-sonnet"):
            shutil.copyfile(path, root / "catalog" / "agents" / path.name)
    (root / "catalog" / "agents" / "judge.json").write_text(json.dumps(
        {"schemaVersion": 1, "id": "judge", "purpose": "old", "provider": "cursor", "model": "grok", "access": "read-only",
         "skills": ["research-judge"]}), encoding="utf-8")
    (root / "catalog" / "agents" / "sceptic-grok.json").write_text(json.dumps(
        {"schemaVersion": 1, "id": "sceptic-grok", "purpose": "old", "provider": "cursor", "model": "grok", "access": "read-only",
         "skills": ["research-sceptic"]}), encoding="utf-8")
    settings = json.loads((REPO / "templates" / "research-center.json").read_text(encoding="utf-8"))
    settings.update({"name": "old_RC", "status": "ready"})
    settings["budget"] = {"ingestCalls": 99, "researchCalls": 24}
    settings["research"] = {"maxSourcesPerResearcher": 7}
    pipeline = settings["pipeline"]
    del pipeline["screener"]
    pipeline.update({"sceptics": ["sceptic-claude", "sceptic-grok"], "researchers": ["researcher-claude"]})
    settings["defaultUseCase"] = "acme"
    (root / "research-center.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    for name, text in (("flake.nix", "{}"), ("nix/tools.nix", "{}"), ("rc", "#!/usr/bin/env bash\nold\n"),
                       ("README.md", "# Our own RC\n"), ("scripts/stale.py", "old\n"),
                       ("research/topic/brief.md", "# A topic\n"), ("docs/our-note.md", "kept\n"),
                       ("usecases/acme/usecase.json", json.dumps({"id": "acme", "title": "Acme scouting", "createdAt": "2026-10-16"})),
                       ("usecases/acme/scope.md", "# Acme\n\nUse case: acme\nStatus: draft\n\n## Who\n\nAcme sells parts [acme.example].\n\nMore.\n"),
                       ("usecases/acme/research/ocr/brief.md", "# OCR\n")):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-qm", "old instance")
    return root


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = old_instance(Path(directory))
        (root / "README.md").write_text("# Edited, not committed\n", encoding="utf-8")
        refused = upgrade(root)
        assert refused.returncode == 1 and "uncommitted changes" in refused.stderr, refused.stderr
        git(root, "checkout", "--", "README.md")

        result = upgrade(root)
        output = result.stdout
        assert "upgraded" in output, output + result.stderr
        assert not (root / "flake.nix").exists() and not (root / "nix").exists(), "Nix files are removed"
        assert (root / "rc.py").read_text(encoding="utf-8") == (REPO / "rc.py").read_text(encoding="utf-8")
        assert "uv run" in (root / "rc").read_text(encoding="utf-8"), "the bash rc is replaced by the uv launcher"
        assert not (root / "scripts" / "stale.py").exists(), "template-owned folders are mirrored"
        # Use cases become profiles, with their history, data and default.
        acme = root / "profiles" / "acme"
        assert not (root / "usecases").exists() and (acme / "research" / "ocr" / "brief.md").is_file() and (acme / "inbox").is_dir()
        profile = json.loads((acme / "profile.json").read_text(encoding="utf-8"))
        assert profile["name"] == "Acme scouting" and profile["type"] == "company" and profile["tags"] == [], profile
        assert profile["description"] == "Acme sells parts.", profile
        assert not (acme / "usecase.json").exists() and "Profile: acme" in (acme / "scope.md").read_text(encoding="utf-8")
        assert "profiles/acme/research/ocr/brief.md" in git(root, "status", "--porcelain"), "moved with git, so history follows"
        assert "use case acme is now profile acme" in output, output
        assert (root / "README.md").read_text(encoding="utf-8") == "# Our own RC\n", "the instance's README stays"
        assert (root / "research" / "topic" / "brief.md").is_file() and (root / "docs" / "our-note.md").is_file(), "data stays"
        assert (root / "catalog" / "evidence-types.json").is_file() and (root / "catalog" / "adapters" / "openalex.json").is_file()

        settings = json.loads((root / "research-center.json").read_text(encoding="utf-8"))
        assert settings.get("defaultProfile") == "acme" and "defaultUseCase" not in settings
        assert settings["budget"]["ingestCalls"] == 99 and settings["budget"]["refreshCalls"] == 16, "added, never overwritten"
        assert settings["research"]["maxSourcesPerResearcher"] == 7 and settings["research"]["snowballDepth"] == 1
        assert settings["pipeline"]["screener"] == "screener" and (root / "catalog" / "agents" / "screener.json").is_file()
        assert settings["pipeline"]["researchers"] == ["researcher-claude"], "a working slot is kept without --reset-roles"
        judge = json.loads((root / "catalog" / "agents" / "judge.json").read_text(encoding="utf-8"))
        grok = json.loads((root / "catalog" / "agents" / "sceptic-grok.json").read_text(encoding="utf-8"))
        assert (judge["provider"], judge["model"]) == ("claude", "opus"), "the template's judge replaces the Cursor one"
        assert (grok["provider"], grok["model"]) == ("claude", "opus"), "a Cursor role without a template twin moves to Claude"
        assert "role judge: cursor is no longer supported" in output, output

        git(root, "add", "-A")
        git(root, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-qm", "upgrade")
        reset = upgrade(root, "--reset-roles")
        settings = json.loads((root / "research-center.json").read_text(encoding="utf-8"))
        assert settings["pipeline"]["researchers"] == ["researcher-claude", "researcher-sonnet"], reset.stdout
        assert settings["pipeline"]["sceptics"] == ["sceptic-claude", "sceptic-sonnet"]
        assert upgrade(REPO).returncode == 1, "the template itself is not an instance"
    print("upgrade instance test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
