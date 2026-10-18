#!/usr/bin/env python3
"""Test the shared trend feed: rc trends init starts trends/ with general tags; it is scouted like a profile, but
every card is judged against all profiles - the evaluator reads each profile, and a card must say which profiles it
may affect, naming only profiles that exist; the main screen shows trends above the profiles with what they may
affect; rc trends tags edits its tags; and the validator checks it like a profile."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path[:0] = [str(HERE), str(SCRIPTS), str(SCRIPTS / "runner"), str(SCRIPTS / "sources"), str(SCRIPTS / "report")]
import home  # noqa: E402
import kit  # noqa: E402
import profiles  # noqa: E402
import profiles_test  # noqa: E402  (its instance builder)
import providers  # noqa: E402
import scout  # noqa: E402

README = "# Harness\n\nHarness runs coding agents with sandboxed tools and parallel subagents, and it records every step for review."
PROMPTS: dict[str, list[str]] = {}


def fake_search(root, adapter, query, filters, since, limit, log):
    if adapter == "github" and "created" in filters and query == "agent harness":
        return [kit.record("github", "acme/harness", "https://github.com/acme/harness", "documentation", date="2026-10-15",
                           abstract="An agent harness", extra={"stars": 3000, "language": "Python", "topics": [], "created": "2026-10-02",
                                                               "archived": False, "license": "Apache-2.0"})]
    return []


def transport(url: str):
    if url.startswith("https://api.github.com/repos/acme/harness/readme"):
        return README.encode("utf-8"), "text/plain"
    raise kit.AdapterError(f"no fixture for {url}")


def fake_run(role, prompt, cwd, log, timeout=0, on_say=None, shared=None):
    PROMPTS.setdefault(role["id"], []).append(prompt)
    if role["id"] == "scout-triage":
        return '```json\n{"picks": [{"id": "K1", "why": "a new agent harness", "component": "how both teams build software"}]}\n```'
    if role["id"] == "scout-evaluator":
        retry = "previous reply was rejected" in prompt
        affects = [{"profile": "alpha" if retry else "gamma", "component": "development workflow", "how": "agents could write and test code"}]
        card = {"verdict": "worth testing", "headline": "An agent harness", "affects": affects,
                "leaders": {"whatItIs": "A harness.", "whatItCouldDo": "Run agents.", "wherePlugsIn": "Development.", "why": "Useful."},
                "engineers": {"howItWorks": "Sandboxes.", "component": "development workflow", "componentToday": "Manual agent runs.",
                              "replaces": "nothing", "alternatives": "Claude Code", "pros": ["sandboxed"], "cons": ["new"], "risks": ["young"],
                              "maturity": "young", "evaluation": {"experiment": "one sprint", "metric": "PRs merged", "passBar": "no regressions", "effort": "S"}},
                "claims": [{"text": "It runs agents.", "quote": "runs coding agents with sandboxed tools and parallel subagents"},
                           {"text": "It records steps.", "quote": "it records every step for review"}],
                "profileBasis": ["../profiles/alpha/profile.json"]}
        return "```json\n" + json.dumps(card) + "\n```"
    if role["id"] == "scout-sceptic":
        card = next(line.split("## Card ", 1)[1] for line in prompt.splitlines() if line.startswith("## Card "))
        assert '"affects"' in prompt and "shared trends" in prompt, prompt
        return '```json\n{"reviews": [{"card": "%s", "verdict": "holds", "issues": []}]}\n```' % card
    raise AssertionError(role["id"])


def quiet(function, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


def main() -> int:
    providers.run = fake_run
    kit.TRANSPORT = transport
    with tempfile.TemporaryDirectory() as directory:
        root = profiles_test.instance(Path(directory))
        shutil.copyfile(SCRIPTS.parent / "templates" / "packs" / "software" / "adapters" / "github.json",
                        root / "catalog" / "adapters" / "github.json")
        quiet(profiles.command_new, root, "alpha", "Alpha Corp", "company", "A forensic investigation firm")
        trends = root / "trends"
        quiet(scout.command_init_trends, trends)
        meta = json.loads((trends / "profile.json").read_text(encoding="utf-8"))
        assert meta["id"] == "trends" and meta["type"] == "company" and "agent harness" in [tag["tag"] for tag in meta["tags"]]
        try:
            scout.command_init_trends(trends)
            raise AssertionError("started twice")
        except scout.rc.RcError as error:
            assert "already exists" in str(error)

        quiet(scout.discover, trends, "2026-10-01", search=fake_search)
        result = quiet(scout.command_run, trends, False)
        assert len(result["cards"]) == 1 and result["failures"] == [], result
        evaluator = PROMPTS["scout-evaluator"]
        assert "shared trends feed" in evaluator[0] and "../profiles/alpha/profile.json" in evaluator[0], evaluator[0]
        assert len(evaluator) == 2 and "use one of the profiles alpha" in evaluator[1], "a card naming no real profile is retried"
        card = scout.all_cards(trends)[0]
        assert card["affects"] == [{"profile": "alpha", "component": "development workflow", "how": "agents could write and test code"}]
        assert "**May affect:** alpha (development workflow): agents could write and test code" in \
            (trends / "scout" / "cards" / f"{card['id']}.md").read_text(encoding="utf-8")

        # The main screen shows trends above the profiles, each with what it may affect, and a page per trend card.
        page, beside = quiet(home.command_home, root)
        text = page.read_text(encoding="utf-8")
        assert text.find('id="trends"') < text.find('id="alpha"') and "May affect: alpha (development workflow)" in text
        assert f"trends/{card['id']}.html" in beside and 'href="trends/' in text

        # rc trends tags edits the feed's tags; the validator checks trends/ like a profile.
        spec = importlib.util.spec_from_file_location("rc_cli", SCRIPTS.parent / "rc.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        cli.ROOT = root
        assert quiet(cli.main, ["trends", "tags", "add", "small language models"]) == 0
        assert "small language models" in [tag["tag"] for tag in json.loads((trends / "profile.json").read_text(encoding="utf-8"))["tags"]]
        validator = profiles_test.load_module("validate_rc", SCRIPTS / "validate-research-center.py")
        assert validator.validate(root) == [], validator.validate(root)
    print("trends test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
