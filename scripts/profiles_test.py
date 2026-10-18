#!/usr/bin/env python3
"""Test profiles: two profiles in one instance keep their sources and research apart and share the instance's
settings, roles and adapters; a profile has a name, a description, a type and tags, and can be edited; research needs
a description or tags; the type sets the licence verdict; rc picks the profile from -p (or the old -u), RC_PROFILE,
defaultProfile or the only one there is; refresh --due covers them all; a leftover usecases/ folder is refused; and
the validator checks each profile."""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path[:0] = [str(HERE), str(HERE / "runner"), str(HERE / "ingest"), str(HERE / "research"), str(HERE / "sources")]
import ingest  # noqa: E402
import licences  # noqa: E402
import profiles  # noqa: E402
import rc  # noqa: E402
import research  # noqa: E402
import sources  # noqa: E402

SCOPE = """# Alpha Corp technology scouting

Profile: alpha
Status: draft

## Who

Alpha Corp, a forensic investigation firm.

## Products and processes

An e-discovery platform: ingest, OCR, search, review. OCR and reranking could be replaced.

## Hard constraints

Data stays in Japan; no internet in production; open licences.

## How value is measured

Reviewer hours saved per case.

## Out of scope

Kernel drivers.

## Scouting lens

Japanese OCR, cross-encoder rerankers.

## Source preferences

Papers and GitHub; distrust vendor benchmarks.
"""


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def quiet(function, *args):
    with redirect_stdout(io.StringIO()):
        return function(*args)


def raises(error: type[BaseException], function, *args) -> str:
    try:
        quiet(function, *args)
    except error as caught:
        return str(caught)
    raise AssertionError(f"{function.__name__} did not raise {error.__name__}")


def instance(base: Path) -> Path:
    root = base / "acme_RC"
    (root / "catalog").mkdir(parents=True)
    for name in ("agents", "adapters"):
        shutil.copytree(REPO / "templates" / name, root / "catalog" / name, copy_function=shutil.copyfile)
    shutil.copytree(REPO / "templates", root / "templates", copy_function=shutil.copyfile)
    shutil.copytree(REPO / ".agents", root / ".agents", copy_function=shutil.copyfile)
    settings = json.loads((REPO / "templates" / "research-center.json").read_text(encoding="utf-8"))
    (root / "research-center.json").write_text(json.dumps({**settings, "name": "acme_RC"}), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def main() -> int:
    with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as bare:
        root = instance(Path(directory))
        # A folder with no research-center.json stands for the template, wherever this test runs.
        assert "template" in raises(ValueError, profiles.command_new, Path(bare), "alpha", "Alpha", "company"), \
            "profiles live in instances"
        quiet(profiles.command_new, root, "alpha", "Alpha Corp", "company", "A forensic investigation firm")
        quiet(profiles.command_new, root, "beta", "Personal learning", "personal")
        assert "already exists" in raises(ValueError, profiles.command_new, root, "alpha", "again", "company")
        assert "hyphen-case" in raises(ValueError, profiles.command_new, root, "Bad Name", "x", "company")
        assert "type must be" in raises(ValueError, profiles.command_new, root, "gamma", "x", "startup")
        alpha, beta = root / "profiles" / "alpha", root / "profiles" / "beta"
        assert profiles.ids(root) == ["alpha", "beta"] and (alpha / "catalog" / "sources").is_dir() and (alpha / "inbox").is_dir()
        meta = profiles.load(root, "alpha")
        assert meta["type"] == "company" and meta["tags"] == [] and meta["description"] == "A forensic investigation firm"

        # Editing changes only what is given.
        quiet(profiles.command_edit, root, "alpha", "Alpha Corp Japan", None, None)
        assert profiles.load(root, "alpha")["name"] == "Alpha Corp Japan" and profiles.load(root, "alpha")["type"] == "company"
        assert "type must be" in raises(ValueError, profiles.command_edit, root, "alpha", None, "startup", None)

        # scope.md is optional; once started, it is accepted only when every section is filled.
        assert "no scope.md" in raises(ValueError, profiles.command_accept, root, "alpha")
        quiet(profiles.command_scope, root, "alpha")
        assert "Profile: alpha" in (alpha / "scope.md").read_text(encoding="utf-8")
        assert "placeholder" in raises(ValueError, profiles.command_accept, root, "alpha")
        (alpha / "scope.md").write_text(SCOPE, encoding="utf-8")
        quiet(profiles.command_accept, root, "alpha")
        assert "Status: accepted" in (alpha / "scope.md").read_text(encoding="utf-8")

        # The type sets the licence verdict: a company may use only permissive licences, a person any.
        assert licences.verdict(alpha, "MIT", "company") == {"spdx": "MIT", "class": "permissive", "usable": True, "reason": ""}
        gpl = licences.verdict(alpha, "GPL-3.0-or-later", "company")
        assert gpl["class"] == "copyleft" and not gpl["usable"] and "same licence" in gpl["reason"], gpl
        assert licences.verdict(alpha, "gpl-3.0", "personal")["usable"], "a personal profile may use any licence"
        assert licences.classify(alpha, "CC-BY-NC-4.0") == "non-commercial" and licences.classify(alpha, "BUSL-1.1") == "source-available"
        unknown = licences.verdict(alpha, "NOASSERTION", "company")
        assert unknown["class"] == "unknown" and not unknown["usable"] and unknown["reason"], unknown
        assert licences.verdict(alpha, None, "company")["class"] == "unknown"
        assert licences.classify(alpha, "LGPL-2.1-only") == "weak-copyleft"

        # Config comes from the instance, data from the profile.
        assert rc.instance(alpha) == root and rc.instance(REPO) == REPO
        assert rc.settings(alpha)["name"] == "acme_RC" and rc.role(alpha, "judge")["provider"] == "claude"
        assert rc.skill_text(alpha, "research-judge").startswith("# Judge"), "skills come from the instance"
        assert sources.descriptors(alpha) == sources.descriptors(root) and "openalex" in sources.descriptors(alpha)
        assert research.evidence_types(alpha)["forum"]["reliabilityCeiling"] == "E"

        # Each profile ingests into its own folder and sees only its own sources.
        for space, name in ((alpha, "alpha-docs"), (beta, "beta-notes")):
            notes = Path(directory) / name
            notes.mkdir()
            (notes / "readme.md").write_text(f"# {name}\n", encoding="utf-8")
            quiet(ingest.command_add, space, argparse.Namespace(kind="folder", locators=[str(notes)], id=name, include=[],
                                                                 exclude=[], note=f"{name} files", depth=1, max_documents=20))
        assert [item["id"] for item in ingest.sources(alpha)] == ["alpha-docs"]
        assert [item["id"] for item in ingest.sources(beta)] == ["beta-notes"]
        assert not (root / "catalog" / "sources").exists(), "nothing lands in the instance root"
        quiet(research.command_new, alpha, argparse.Namespace(topic="ocr", title="Japanese OCR for review"))
        text = research.context(alpha, "ocr")
        assert "Profile: profile.json" in text and "a company profile: only permissive licences" in text, text
        assert "Scope: scope.md" in text and "alpha-docs" in text and "beta-notes" not in text, text
        assert "a personal profile: any licence" in research.context(beta, "x")
        assert (alpha / "research" / "ocr" / "brief.md").is_file() and not (root / "research").exists()

        # Research needs a description or tags, so its results can be judged against whom they serve.
        quiet(research.command_new, beta, argparse.Namespace(topic="habits", title="Habits"))
        assert "no description and no interest tags" in raises(rc.RcError, research.run_research, beta, "habits", None, None)

        # rc chooses the profile: -p (or the old -u), RC_PROFILE, defaultProfile, the only one; several without a choice
        # is an error.
        cli = load_module("rc_cli", REPO / "rc.py")
        cli.ROOT = root
        for name in ("RC_PROFILE", "RC_USE_CASE"):
            os.environ.pop(name, None)
        assert cli.data_root("beta") == beta
        assert "several profiles" in raises(SystemExit, cli.data_root, None)
        os.environ["RC_PROFILE"] = "alpha"
        assert cli.data_root(None) == alpha
        os.environ.pop("RC_PROFILE")
        settings = json.loads((root / "research-center.json").read_text(encoding="utf-8"))
        (root / "research-center.json").write_text(json.dumps({**settings, "defaultProfile": "beta"}), encoding="utf-8")
        assert cli.data_root(None) == beta
        assert "no profile gamma" in raises(SystemExit, cli.data_root, "gamma")
        assert quiet(cli.main, ["research", "refresh", "--due"]) == 0, "refresh --due covers every profile"
        assert quiet(cli.main, ["-u", "alpha", "research", "list"]) == 0 and quiet(cli.main, ["-p", "alpha", "research", "list"]) == 0
        (root / "usecases").mkdir()
        assert "rc upgrade" in raises(SystemExit, cli.data_root, "alpha"), "a leftover usecases/ folder is refused"

        # The validator checks every profile and refuses the old layout; the template ships none.
        validator = load_module("validate_rc", HERE / "validate-research-center.py")
        assert "usecases/ is the layout from before profiles" in " ".join(validator.validate(root))
        (root / "usecases").rmdir()
        assert validator.validate(root) == [], validator.validate(root)
        meta = json.loads((beta / "profile.json").read_text(encoding="utf-8"))
        (beta / "profile.json").write_text(json.dumps({**meta, "id": "other", "type": "startup"}), encoding="utf-8")
        (alpha / "scope.md").write_text(SCOPE.replace("Status: draft", "Status: accepted").replace("Kernel drivers.", "<later>"),
                                        encoding="utf-8")
        errors = " ".join(validator.validate(root))
        assert "profiles/beta/profile.json: id must equal" in errors and "profiles/beta/profile.json: type must be" in errors, errors
        assert "profiles/alpha/scope.md: section '## Out of scope'" in errors, errors
        hooks = load_module("hooks", HERE / "rule_hooks.py")
        assert hooks.markdown_allowed("profiles/alpha/scope.md") and hooks.markdown_allowed("profiles/alpha/research/ocr/brief.md")
    print("profiles test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
