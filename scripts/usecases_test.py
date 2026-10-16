#!/usr/bin/env python3
"""Test use cases: two use cases in one instance keep their sources and research apart, share the instance's
settings, roles and adapters, research needs an accepted scope, rc picks the use case from -u, RC_USE_CASE,
defaultUseCase or the only one there is, refresh --due covers them all, and the validator checks each."""

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
import rc  # noqa: E402
import research  # noqa: E402
import sources  # noqa: E402
import usecases  # noqa: E402

SCOPE = """# Alpha Corp technology scouting

Use case: alpha
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
        assert "template" in raises(ValueError, usecases.command_new, Path(bare), "alpha", "Alpha"), "use cases live in instances"
        quiet(usecases.command_new, root, "alpha", "Alpha Corp technology scouting")
        quiet(usecases.command_new, root, "beta", "Personal learning")
        assert "already exists" in raises(ValueError, usecases.command_new, root, "alpha", "again")
        assert "hyphen-case" in raises(ValueError, usecases.command_new, root, "Bad Name", "x")
        alpha, beta = root / "usecases" / "alpha", root / "usecases" / "beta"
        assert usecases.ids(root) == ["alpha", "beta"] and (alpha / "catalog" / "sources").is_dir()

        # A scope is accepted only when every section is filled.
        assert "placeholder" in raises(ValueError, usecases.command_accept, root, "alpha")
        (alpha / "scope.md").write_text(SCOPE, encoding="utf-8")
        quiet(usecases.command_accept, root, "alpha")
        assert "Status: accepted" in (alpha / "scope.md").read_text(encoding="utf-8")

        # Config comes from the instance, data from the use case.
        assert rc.instance(alpha) == root and rc.instance(REPO) == REPO
        assert rc.settings(alpha)["name"] == "acme_RC" and rc.role(alpha, "judge")["provider"] == "claude"
        assert rc.skill_text(alpha, "research-judge").startswith("# Judge"), "skills come from the instance"
        assert sources.descriptors(alpha) == sources.descriptors(root) and "openalex" in sources.descriptors(alpha)
        assert research.evidence_types(alpha)["forum"]["reliabilityCeiling"] == "E"

        # Each use case ingests into its own folder and sees only its own sources.
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
        assert "Use case scope: scope.md" in text and "alpha-docs" in text and "beta-notes" not in text, text
        assert (alpha / "research" / "ocr" / "brief.md").is_file() and not (root / "research").exists()

        # Research needs an accepted scope.
        quiet(research.command_new, beta, argparse.Namespace(topic="habits", title="Habits"))
        assert "not accepted" in raises(rc.RcError, research.run_research, beta, "habits", None, None)

        # rc chooses the use case: -u, RC_USE_CASE, defaultUseCase, the only one; several without a choice is an error.
        cli = load_module("rc_cli", REPO / "rc.py")
        cli.ROOT = root
        os.environ.pop("RC_USE_CASE", None)
        assert cli.data_root("beta") == beta
        assert "several use cases" in raises(SystemExit, cli.data_root, None)
        os.environ["RC_USE_CASE"] = "alpha"
        assert cli.data_root(None) == alpha
        os.environ.pop("RC_USE_CASE")
        settings = json.loads((root / "research-center.json").read_text(encoding="utf-8"))
        (root / "research-center.json").write_text(json.dumps({**settings, "defaultUseCase": "beta"}), encoding="utf-8")
        assert cli.data_root(None) == beta
        assert "no use case gamma" in raises(SystemExit, cli.data_root, "gamma")
        assert quiet(cli.main, ["research", "refresh", "--due"]) == 0, "refresh --due covers every use case"

        # The validator checks every use case, and the template ships none.
        validator = load_module("validate_rc", HERE / "validate-research-center.py")
        assert validator.validate(root) == [], validator.validate(root)
        meta = json.loads((beta / "usecase.json").read_text(encoding="utf-8"))
        (beta / "usecase.json").write_text(json.dumps({**meta, "id": "other"}), encoding="utf-8")
        (alpha / "scope.md").write_text(SCOPE.replace("Status: draft", "Status: accepted").replace("Kernel drivers.", "<later>"),
                                        encoding="utf-8")
        errors = " ".join(validator.validate(root))
        assert "usecases/beta/usecase.json: id must equal" in errors and "usecases/alpha/scope.md: section '## Out of scope'" in errors, errors
        hooks = load_module("hooks", HERE / "rule_hooks.py")
        assert hooks.markdown_allowed("usecases/alpha/scope.md") and hooks.markdown_allowed("usecases/alpha/research/ocr/brief.md")
    print("use cases test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
