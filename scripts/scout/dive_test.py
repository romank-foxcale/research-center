#!/usr/bin/env python3
"""Test the weekly schedule and deep dives: a profile is due when it has tags and its last full scout is
scout.cadenceDays or more ago; rc scout --due runs every due profile and the trend feed and skips the rest; and
rc scout dive turns a card into a draft research brief that passes the brief check, pre-filled from the card, with
the card marked as dived - never from a trend card, never over an existing topic."""

from __future__ import annotations

import datetime
import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path[:0] = [str(HERE), str(SCRIPTS), str(SCRIPTS / "runner"), str(SCRIPTS / "research"), str(SCRIPTS / "report")]
import home_test  # noqa: E402  (its card builder)
import profiles  # noqa: E402
import profiles_test  # noqa: E402  (its instance builder)
import research  # noqa: E402
import scout  # noqa: E402
import tags  # noqa: E402


def quiet(function, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


def raises(function, *args) -> str:
    try:
        quiet(function, *args)
    except scout.rc.RcError as error:
        return str(error)
    raise AssertionError(f"{function.__name__} did not raise")


def test_dive(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = profiles_test.instance(Path(directory))
        quiet(profiles.command_new, root, "alpha", "Alpha Corp", "company", "A forensic investigation firm")
        alpha = root / "profiles" / "alpha"
        today = datetime.date(2026, 10, 18)

        # Due: tags and a cadence that has passed (or no full scout yet).
        assert not scout.is_due(alpha, today), "a profile without tags is never due"
        quiet(tags.command_add, alpha, "Japanese OCR")
        assert scout.is_due(alpha, today), "never scouted: due"
        (alpha / "scout").mkdir()
        (alpha / "scout" / "state.json").write_text(json.dumps({"lastRun": "2026-10-15"}), encoding="utf-8")
        assert not scout.is_due(alpha, today) and scout.is_due(alpha, datetime.date(2026, 10, 22)), "due after 7 days"

        # rc scout --due goes through every profile and the trend feed, and runs none that is not due.
        quiet(scout.command_init_trends, root / "trends")
        (root / "trends" / "scout").mkdir()
        (root / "trends" / "scout" / "state.json").write_text(
            json.dumps({"lastRun": datetime.date.today().isoformat()}), encoding="utf-8"
        )
        (alpha / "scout" / "state.json").write_text(
            json.dumps({"lastRun": datetime.date.today().isoformat()}), encoding="utf-8"
        )
        spec = importlib.util.spec_from_file_location("rc_cli", SCRIPTS.parent / "rc.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        monkeypatch.setattr(cli, "ROOT", root)
        assert quiet(cli.main, ["scout", "--due"]) == 0

        # A deep dive: a draft brief from the card, which passes the brief check, and the card remembers it.
        (alpha / "scout" / "cards").mkdir()
        card = home_test.card("acme-ocr", "acme/ocr-kit", "worth testing")
        (alpha / "scout" / "cards" / "acme-ocr.json").write_text(json.dumps(card), encoding="utf-8")
        brief = quiet(scout.command_dive, alpha, "acme-ocr")
        assert brief == alpha / "research" / "ocr-kit" / "brief.md", brief
        text = brief.read_text(encoding="utf-8")
        assert research.brief_problems(text) == [], research.brief_problems(text)
        assert "# Should acme/ocr-kit change DI OCR?" in text and "Status: draft" in text
        assert (
            "- Q1: Does acme/ocr-kit do better than what DI OCR does today, measured as character error rate, on data like ours?"
            in text
        )
        assert "Today: Tesseract. Alternatives: PaddleOCR" in text
        assert (
            "pass bar below 3%" in text
            and "Cadence: none" in text
            and "Its licence (MIT, permissive) is usable" in text
        )
        dived = json.loads((alpha / "scout" / "cards" / "acme-ocr.json").read_text(encoding="utf-8"))
        assert dived["status"] == "deep dive" and dived["research"] == "ocr-kit"
        assert "already exists" in raises(scout.command_dive, alpha, "acme-ocr")
        assert "no card" in raises(scout.command_dive, alpha, "nothing")
        (root / "trends" / "scout" / "cards").mkdir(parents=True)
        (root / "trends" / "scout" / "cards" / "t.json").write_text(json.dumps(card), encoding="utf-8")
        assert "from the profile it affects" in raises(scout.command_dive, root / "trends", "t")
