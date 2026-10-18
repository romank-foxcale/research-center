#!/usr/bin/env python3
"""Test interest tags: added, renamed and removed by the user, never twice; proposed by the tagger with a reason and
evidence the runner checks (a proposal citing a missing file is retried); accepted or rejected, a rejected tag never
proposed again; tags need a profile; and a profile's inbox/ is registered as a source once it holds a file."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "runner"), str(HERE / "ingest")]
import ingest  # noqa: E402
import profiles  # noqa: E402
import profiles_test  # noqa: E402  (its instance builder)
import providers  # noqa: E402
import rc  # noqa: E402
import tags  # noqa: E402

PROMPTS: list[str] = []


def block(data) -> str:
    return "Here are the tags.\n\n```json\n" + json.dumps(data) + "\n```\n"


def fake_run(role, prompt, cwd, log, timeout=0, on_say=None, shared=None):
    assert role["id"] == "tagger", role["id"]
    PROMPTS.append(prompt)
    retry = "previous reply was rejected" in prompt
    evidence = "knowledge/profile/ocr.md" if retry or len(PROMPTS) > 2 else "knowledge/profile/missing.md"
    proposals = [{"tag": "Japanese OCR", "why": "scanned Japanese documents are read with Tesseract", "evidence": [evidence]},
                 {"tag": "cross-encoder reranking", "why": "the reranker is a placeholder", "evidence": ["profile.json"]},
                 {"tag": "blockchain", "why": "adjacent", "evidence": ["profile.json"]}]
    if len(PROMPTS) > 2:  # a later run must leave out what was taken or rejected
        assert "Rejected before, never propose again: blockchain" in prompt and "Current tags:" in prompt, prompt
        proposals = [{"tag": "near-duplicate detection", "why": "review sets hold many copies", "evidence": [evidence]}]
    return block({"tags": proposals})


def quiet(function, *args):
    with redirect_stdout(io.StringIO()):
        return function(*args)


def raises(function, *args) -> str:
    try:
        quiet(function, *args)
    except rc.RcError as error:
        return str(error)
    raise AssertionError(f"{function.__name__} did not raise")


def main() -> int:
    providers.run = fake_run
    with tempfile.TemporaryDirectory() as directory:
        root = profiles_test.instance(Path(directory))
        assert "tags belong to a profile" in raises(tags.command_list, root)
        quiet(profiles.command_new, root, "alpha", "Alpha Corp", "company", "A forensic investigation firm")
        alpha = root / "profiles" / "alpha"

        # The user's own tags: added once, renamed, removed.
        quiet(tags.command_add, alpha, "  digital   forensics ", "our domain")
        assert "already a tag" in raises(tags.command_add, alpha, "Digital Forensics")
        assert "words or fewer" in raises(tags.command_add, alpha, "a very long tag that nobody could search")
        quiet(tags.command_rename, alpha, "digital forensics", "Digital forensics")
        quiet(tags.command_add, alpha, "e-discovery")
        quiet(tags.command_remove, alpha, "E-Discovery")
        meta = tags.load(alpha)
        assert tags.names(meta["tags"]) == ["Digital forensics"] and meta["tags"][0]["source"] == "user" and meta["tags"][0]["why"] == "our domain"
        assert "no tag" in raises(tags.command_remove, alpha, "nothing")

        # Proposals rest on files of the profile: a reply citing a missing file is retried once.
        (alpha / "knowledge" / "profile" / "ocr.md").write_text("# OCR\n", encoding="utf-8")
        proposals = quiet(tags.command_suggest, alpha)
        assert len(PROMPTS) == 2 and "missing.md, which is not a file of this profile" in PROMPTS[1], PROMPTS[-1][-400:]
        assert "Read profile.json" in PROMPTS[0] and "Current tags: Digital forensics" in PROMPTS[0]
        assert [item["tag"] for item in proposals] == ["Japanese OCR", "cross-encoder reranking", "blockchain"]
        assert tags.load(alpha)["tags"] == meta["tags"], "proposals wait until accepted"
        problems = tags.suggestion_problems({"tags": [{"tag": "digital forensics", "why": "x", "evidence": ["profile.json"]},
                                                      {"tag": "a", "why": "", "evidence": []}]}, alpha, {"digital forensics"})
        assert "already a tag or was rejected" in problems[0] and "needs a why" in problems[1] and "needs evidence" in problems[2], problems

        # Accept some, reject one; a rejected tag is never proposed again, and adding it by hand un-rejects it.
        quiet(tags.command_accept, alpha, ["japanese ocr", "Cross-encoder reranking"])
        quiet(tags.command_reject, alpha, ["blockchain"])
        meta = tags.load(alpha)
        assert tags.names(meta["tags"]) == ["Digital forensics", "Japanese OCR", "cross-encoder reranking"]
        assert meta["tags"][1]["source"] == "agent" and meta["tags"][1]["evidence"] == ["knowledge/profile/ocr.md"]
        assert meta["suggestedTags"] == [] and meta["rejectedTags"] == ["blockchain"]
        assert "no proposed tag" in raises(tags.command_accept, alpha, ["blockchain"])
        quiet(tags.command_suggest, alpha)
        quiet(tags.command_accept, alpha, [], True)
        assert "near-duplicate detection" in tags.names(tags.load(alpha)["tags"])
        assert profiles.meta_problems(tags.load(alpha), "alpha") == [], "profile.json stays valid"

        # A profile's inbox/ becomes a source once it holds a file; its locator is relative, so it works on any clone.
        assert ingest.ensure_inbox(alpha) is None, "an empty inbox is not a source"
        (alpha / "inbox" / "about-us.md").write_text("# Alpha Corp\n\nWe investigate fraud.\n", encoding="utf-8")
        descriptor = ingest.ensure_inbox(alpha)
        assert descriptor["locators"] == ["inbox"] and (alpha / "catalog" / "sources" / "inbox.json").is_file()
        assert ingest.ensure_inbox(alpha) is None, "registered once"
        assert ingest.local_folder(alpha, "inbox") == alpha / "inbox" and ingest.folder_files(ingest.local_folder(alpha, "inbox")) == ["about-us.md"]
    print("tags test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
