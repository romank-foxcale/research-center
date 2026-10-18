#!/usr/bin/env python3
"""Test triage, technology cards and their challenge, on the case that motivated them: a hosted engine whose README
says it replaces TAR review. Triage picks it and a copyleft OCR repository and passes the noise; the runner stores
each README as evidence and sets the licence line; a card whose quote is not in the evidence is retried; the sceptic
turns the hosted engine's card into "not a fit" and the card says the sceptic changed it; the copyleft repository's
card says the company cannot ship it; the seen-list records cards and passes; dismissing a card closes it for good;
and a run with nothing open costs no call."""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path[:0] = [str(HERE), str(SCRIPTS), str(SCRIPTS / "runner"), str(SCRIPTS / "sources")]
import kit  # noqa: E402
import profiles  # noqa: E402
import profiles_test  # noqa: E402  (its instance builder)
import providers  # noqa: E402
import scout  # noqa: E402
import tags  # noqa: E402

READMES = {
    "jev/jev": "# JEV\n\nJEV is a hosted relevance engine for legal review. Every document is sent to our scoring API "
               "for classification, and it replaces keyword review and TAR workflows entirely.",
    "gpl/ocr": "# GPL OCR\n\nGPL OCR reads Japanese scanned documents with layout analysis and reading order detection, "
               "and it runs fully offline on one GPU.",
}
CALLS: list[str] = []


def repo(name: str, licence: str, stars: int) -> dict:
    return kit.record("github", name, f"https://github.com/{name}", "documentation", date="2026-10-15",
                      abstract=f"{name} summary", extra={"stars": stars, "language": "Python", "topics": [], "created": "2026-10-01",
                                                          "archived": False, "license": licence})


def fake_search(root, adapter, query, filters, since, limit, log):
    if adapter == "github" and "created" in filters:
        return [repo("jev/jev", "MIT", 4000), repo("gpl/ocr", "GPL-3.0", 900), repo("awesome/list", "MIT", 100)]
    return []


def transport(url: str):
    for name, text in READMES.items():
        if url.startswith(f"https://api.github.com/repos/{name}/readme"):
            return text.encode("utf-8"), "text/plain"
    raise kit.AdapterError(f"no fixture for {url}")


def card(verdict: str, quotes: list[str], component: str) -> dict:
    return {"verdict": verdict, "headline": f"{component}: {verdict}",
            "leaders": {"whatItIs": "A tool.", "whatItCouldDo": "Maybe help.", "wherePlugsIn": component, "why": "Because."},
            "engineers": {"howItWorks": "It works.", "component": component, "componentToday": "TF-IDF and logistic regression.",
                          "replaces": "the ranker", "alternatives": "what we have", "pros": ["fast"], "cons": ["new"],
                          "risks": ["unproven"], "maturity": "young",
                          "evaluation": {"experiment": "replay project 1", "metric": "reads to 80% recall", "passBar": "10% fewer", "effort": "S"}},
            "claims": [{"text": f"claim {number}", "quote": quote} for number, quote in enumerate(quotes, 1)],
            "profileBasis": ["profile.json", "scope.md"]}


def fake_run(role, prompt, cwd, log, timeout=0, on_say=None, shared=None):
    CALLS.append(role["id"])
    retry = "previous reply was rejected" in prompt
    if role["id"] == "scout-triage":
        lines = [line for line in prompt.splitlines() if line.startswith("K")]
        ids = {line.split(" | ")[1]: line.split(" | ")[0] for line in lines}
        assert "Read profile.json, scope.md" in prompt and len(lines) == 3, prompt
        return "```json\n" + json.dumps({"picks": [{"id": ids["jev/jev"], "why": "it claims to replace TAR", "component": "FLAR"},
                                                   {"id": ids["gpl/ocr"], "why": "Japanese OCR", "component": "DI OCR"}]}) + "\n```"
    if role["id"] == "scout-evaluator":
        if "Find: jev/jev" in prompt:
            assert "Licence (set by the runner, not by you): MIT, class permissive, usable by this profile." in prompt, prompt
            return "```json\n" + json.dumps(card("worth testing", ["Every document is sent to our scoring API for classification",
                                                                   "it replaces keyword review and TAR workflows entirely"], "FLAR")) + "\n```"
        assert "NOT usable by this company profile" in prompt, prompt
        quote = "reads Japanese scanned documents with layout analysis" if retry else "a sentence the readme never says at all"
        return "```json\n" + json.dumps(card("watch", [quote, "it runs fully offline on one GPU"], "DI OCR")) + "\n```"
    if role["id"] == "scout-sceptic":
        cards = [line.split("## Card ", 1)[1] for line in prompt.splitlines() if line.startswith("## Card ")]
        jev = next(name for name in cards if "jev" in name)
        ocr = next(name for name in cards if "ocr" in name)
        return "```json\n" + json.dumps({"reviews": [
            {"card": jev, "verdict": "wrong", "suggestedVerdict": "not a fit",
             "issues": ["It sends every document to a hosted API, which the scope forbids for client data."]},
            {"card": ocr, "verdict": "holds", "issues": []}]}) + "\n```"
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
        alpha = root / "profiles" / "alpha"
        (alpha / "scope.md").write_text(profiles_test.SCOPE, encoding="utf-8")
        quiet(tags.command_add, alpha, "technology-assisted review")
        quiet(scout.discover, alpha, "2026-10-01", search=fake_search)

        result = quiet(scout.command_run, alpha, False)
        assert CALLS == ["scout-triage", "scout-evaluator", "scout-evaluator", "scout-evaluator", "scout-sceptic"] or \
            sorted(CALLS) == sorted(["scout-triage", "scout-evaluator", "scout-evaluator", "scout-evaluator", "scout-sceptic"]), CALLS
        assert result["triaged"] == 3 and len(result["cards"]) == 2 and result["failures"] == [] and result["calls"] == 5, result

        cards = {card["title"]: card for card in scout.all_cards(alpha)}
        jev, ocr = cards["jev/jev"], cards["gpl/ocr"]
        assert jev["verdict"] == "not a fit" and jev["verdictBy"] == "sceptic" and jev["evaluatorVerdict"] == "worth testing"
        page = (alpha / "scout" / "cards" / f"{jev['id']}.md").read_text(encoding="utf-8")
        assert "**Verdict: not a fit.**" in page and "The sceptic changed the verdict from \"worth testing\"" in page, page
        assert "## In plain words" in page and "## For engineers" in page and "Pass bar: 10% fewer" in page
        assert "hosted API, which the scope forbids" in page
        assert ocr["verdict"] == "watch" and ocr["review"]["verdict"] == "holds" and not ocr["licence"]["usable"]
        ocr_page = (alpha / "scout" / "cards" / f"{ocr['id']}.md").read_text(encoding="utf-8")
        assert "**not usable for this profile:**" in ocr_page and "same licence" in ocr_page, ocr_page
        evidence = (alpha / jev["evidence"]).read_text(encoding="utf-8")
        assert "Every document is sent to our scoring API" in evidence and "- Licence: MIT (permissive)" in evidence

        # The seen-list: picks became cards, the rest was passed; nothing is open, so the next run costs nothing.
        seen = json.loads((alpha / "scout" / "seen.json").read_text(encoding="utf-8"))
        assert sorted(entry["status"] for entry in seen.values()) == ["card", "card", "passed"], seen
        CALLS.clear()
        assert quiet(scout.command_run, alpha, False)["triaged"] == 0 and CALLS == []

        # Dismissing closes a card for good.
        quiet(scout.command_dismiss, alpha, jev["id"])
        assert scout.all_cards(alpha)[0]["status"] in ("open", "dismissed")
        assert {card["title"]: card["status"] for card in scout.all_cards(alpha)}["jev/jev"] == "dismissed"
        assert json.loads((alpha / "scout" / "seen.json").read_text(encoding="utf-8"))[jev["key"]]["status"] == "dismissed"
    print("cards test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
