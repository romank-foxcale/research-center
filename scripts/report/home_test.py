#!/usr/bin/env python3
"""Test the main screen: every profile with its type, tags and open cards grouped by verdict (worth testing, watch,
not a fit), dismissed cards left out and counted, a licence the profile cannot use and a verdict the sceptic changed
flagged on the tile; one page per card with plain words before the engineers' part and a link back; each profile's
research dashboard and topic pages beside it, linked up; text escaped; and a share manifest with a content-only main
page and whole pages beside it."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent / "runner")]
import home  # noqa: E402
import profiles  # noqa: E402
import profiles_test  # noqa: E402  (its instance builder)
import report_test  # noqa: E402  (its research topic fixture)


def card(identifier: str, title: str, verdict: str, **extra) -> dict:
    return {
        "id": identifier,
        "stamp": "2026-10-18",
        "key": f"url:{identifier}",
        "title": title,
        "url": f"https://github.com/{identifier}",
        "kind": "repository",
        "date": "2026-10-18",
        "tags": ["Japanese OCR"],
        "status": "open",
        "licence": {"spdx": "MIT", "class": "permissive", "usable": True, "reason": ""},
        "evidence": f"scout/evidence/{identifier}.md",
        "verdict": verdict,
        "verdictBy": "evaluator",
        "evaluatorVerdict": verdict,
        "headline": f"{title} in one line",
        "leaders": {
            "whatItIs": "An OCR engine.",
            "whatItCouldDo": "Read scans.",
            "wherePlugsIn": "DI OCR",
            "why": "Fits.",
        },
        "engineers": {
            "howItWorks": "Layout model.",
            "component": "DI OCR",
            "componentToday": "Tesseract.",
            "replaces": "Tesseract",
            "alternatives": "PaddleOCR",
            "pros": ["accurate"],
            "cons": ["new"],
            "risks": ["licence"],
            "maturity": "young",
            "evaluation": {
                "experiment": "OCR 200 scans",
                "metric": "character error rate",
                "passBar": "below 3%",
                "effort": "S",
            },
        },
        "claims": [{"text": "It reads Japanese.", "quote": "reads Japanese scanned documents with layout"}],
        "profileBasis": ["profile.json"],
        "review": {"verdict": "holds", "issues": [], "suggestedVerdict": None},
        **extra,
    }


def quiet(function, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = profiles_test.instance(Path(directory))
        quiet(profiles.command_new, root, "alpha", "Alpha Corp", "company", "A forensic investigation firm")
        quiet(profiles.command_new, root, "beta", "Me", "personal")
        alpha = root / "profiles" / "alpha"
        report_test.fixture(alpha)  # a research topic; it overwrites profile.json, which is restored below
        (alpha / "profile.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "id": "alpha",
                    "name": "Alpha Corp",
                    "type": "company",
                    "description": "A forensic investigation firm",
                    "tags": [{"tag": "Japanese OCR"}, {"tag": "e-discovery"}],
                }
            ),
            encoding="utf-8",
        )
        cards = alpha / "scout" / "cards"
        cards.mkdir(parents=True)
        for item in (
            card("good-ocr", "Good <script>alert(1)</script> OCR", "worth testing"),
            card(
                "hosted-engine",
                "Hosted engine",
                "not a fit",
                verdictBy="sceptic",
                evaluatorVerdict="worth testing",
                review={
                    "verdict": "wrong",
                    "issues": ["Sends documents to a hosted API."],
                    "suggestedVerdict": "not a fit",
                },
            ),
            card(
                "gpl-tool",
                "GPL tool",
                "watch",
                licence={
                    "spdx": "GPL-3.0",
                    "class": "copyleft",
                    "usable": False,
                    "reason": "must be released under the same licence",
                },
            ),
            card("old-thing", "Old thing", "watch", status="dismissed"),
        ):
            (cards / f"{item['id']}.json").write_text(json.dumps(item), encoding="utf-8")
        (alpha / "scout" / "state.json").write_text(json.dumps({"lastDiscovery": "2026-10-18"}), encoding="utf-8")

        main_page, beside = quiet(home.command_home, root)
        assert main_page == root / ".rc-local" / "reports" / "home" / "index.html"
        text = main_page.read_text(encoding="utf-8")
        # Profiles, their type and tags; cards grouped by verdict in the order a reader acts on.
        assert "Alpha Corp" in text and "Me</h2>" in text and "status-company" in text and "status-personal" in text
        assert (
            "Japanese OCR</span>" in text
            and "4 profiles" not in text
            and "2 profiles" in text
            and "3 open cards" in text
        )
        positions = [
            text.find(f'<span class="badge verdict-{name}">') for name in ("worth-testing", "watch", "not-a-fit")
        ]
        assert all(position > 0 for position in positions) and positions == sorted(positions), positions
        assert "Old thing" not in text and "1 dismissed" in text and "last scouted 2026-10-18" in text
        assert "licence GPL-3.0: not usable" in text and "verdict changed by the sceptic" in text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text and "<script>alert" not in text
        assert 'href="alpha/good-ocr.html"' in text and 'href="alpha/research/index.html"' in text
        assert "No technology cards yet: run rc -p beta scout" in text

        # One page per open card: plain words first, engineers after, sceptic and evidence, and a way back.
        assert (
            set(beside)
            >= {
                "alpha/good-ocr.html",
                "alpha/hosted-engine.html",
                "alpha/gpl-tool.html",
                "alpha/research/index.html",
                "alpha/research/retrieval.html",
            }
            and "alpha/old-thing.html" not in beside
        ), beside
        engine = Path(beside["alpha/hosted-engine.html"]).read_text(encoding="utf-8")
        assert (
            engine.find("What it is")
            < engine.find("For engineers")
            < engine.find("How to evaluate it")
            < engine.find("Sceptic")
        )
        assert (
            'The sceptic changed the verdict from "worth testing" to "not a fit".' in engine
            and "Sends documents to a hosted API." in engine
        )
        assert '<a href="../index.html">&larr; Main screen</a>' in engine and "below 3%" in engine
        gpl = Path(beside["alpha/gpl-tool.html"]).read_text(encoding="utf-8")
        assert "not usable for a company profile:</b> must be released under the same licence" in gpl
        research = Path(beside["alpha/research/index.html"]).read_text(encoding="utf-8")
        assert '<a href="../../index.html">&larr; Main screen</a>' in research and 'href="retrieval.html"' in research

        # The share manifest: a content-only main page, whole pages beside it, the title.
        content = home.render_home(root, fragment=True)
        assert content.startswith("<title>") and "<!doctype" not in content
        assert all(Path(path).read_text(encoding="utf-8").startswith("<!doctype html>") for path in beside.values())
    print("home test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
