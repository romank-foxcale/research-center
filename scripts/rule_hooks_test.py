#!/usr/bin/env python3
"""Test the rule hooks: each hard rule has a case it must stop and a look-alike it must let through."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import rule_hooks
from rule_hooks import ai_attribution, markdown_allowed, post_edit, pre_bash, pre_edit, stop

SCRIPT = Path(__file__).resolve().parent / "rule_hooks.py"


def decision(result: dict | None) -> str | None:
    return result["hookSpecificOutput"]["permissionDecision"] if result else None


def bash(command: str, cwd: Path | None = None) -> str | None:
    return decision(pre_bash({"tool_input": {"command": command}, "cwd": str(cwd or ".")}))


def check_attribution(base: Path) -> None:
    trailer = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    assert ai_attribution(f"Fix parser\n\n{trailer}\n") == trailer
    assert (
        ai_attribution("Fix parser\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)")
        == "Generated with [Claude Code](https://claude.com/claude-code)"
    )
    assert ai_attribution(f'git commit -m "Fix" -m "{trailer}"') == trailer, "the trailer alone, without -m"
    assert ai_attribution("Fix parser\n\nCo-authored-by: Jane Doe <jane@example.com>") is None, (
        "human co-authors are fine"
    )
    assert ai_attribution("Block 'Generated with Claude' footers in PR bodies") is None, "prose about the rule is fine"

    assert bash(f"git commit -m \"$(cat <<'EOF'\nFix parser\n\n{trailer}\nEOF\n)\"") == "deny", "heredoc message"
    assert bash(f'git -C ../worktrees/f/api_wt commit -m "Fix" -m "{trailer}"') == "deny", "second -m argument"
    assert bash('gh pr create --title T --body "Summary\n\n🤖 Generated with Claude Code"') == "deny", "PR body"
    (base / "msg.txt").write_text(f"Fix parser\n\n{trailer}\n", encoding="utf-8")
    assert bash("git commit -F msg.txt", base) == "deny", "message file"
    assert bash('git commit -m "Fix parser"') is None
    assert bash(f"grep -rn '{trailer}' docs") is None, "not a commit"


def check_markdown_allowlist() -> None:
    for path in ("README.md", "docs/hacks/x.md", "plans/active/p.md", ".agents/skills/s/SKILL.md", "templates/note.md"):
        assert markdown_allowed(path), path
    for path in ("NOTES.md", "scripts/README.md", "templates/sub/x.md", "docs.md", "nix/projects/api.md"):
        assert not markdown_allowed(path), path
    assert markdown_allowed("research/plan/01.md", ("research/",))
    assert not markdown_allowed("research-old/01.md", ("research/",)), "a declared folder is a folder, not a prefix"


def edit(root: Path, path: str, tool: str = "Write") -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": str(root / path)}, "cwd": str(root)}


def check_edits(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text("/.notes/\n")
    (root / "scripts").mkdir()
    (root / "scripts" / "OLD.md").write_text("tracked before the rule\n")

    result = pre_edit(edit(root, ".claude/skills/tdd/SKILL.md", "Edit"), root)
    assert (
        decision(result) == "deny"
        and ".agents/skills/tdd/SKILL.md" in result["hookSpecificOutput"]["permissionDecisionReason"]
    )
    assert decision(pre_edit(edit(root, "NOTES.md"), root)) == "deny", "a new stray Markdown file"
    assert pre_edit(edit(root, "docs/hacks/x.md"), root) is None
    assert pre_edit(edit(root, ".notes/scratch.md"), root) is None, "ignored local notes are not tracked"
    assert pre_edit(edit(root, "scripts/OLD.md"), root) is None, "an existing file is the gate's business"
    assert pre_edit(edit(root, "scripts/x.py"), root) is None
    assert decision(pre_edit(edit(root, "notes/a.md"), root)) == "deny", "undeclared folder"
    (root / "research-center.json").write_text(json.dumps({"markdownDirs": ["notes"]}))
    assert pre_edit(edit(root, "notes/a.md"), root) is None, "a folder the RC declares in markdownDirs"
    assert decision(pre_edit(edit(root, "NOTES.md"), root)) == "deny", "declaring one folder allows only that folder"
    (root / "research-center.json").write_text("not json")
    assert decision(pre_edit(edit(root, "notes/a.md"), root)) == "deny", "a broken manifest declares nothing"
    assert (
        pre_edit({"tool_name": "Write", "tool_input": {"file_path": str(root.parent / "elsewhere.md")}}, root) is None
    ), "outside the RC: worktrees, scratchpad, memory"


def check_notes_and_drift() -> None:
    """Run against a copy of this RC so the real validator and drift check are exercised."""
    source = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "cc"
        files = subprocess.run(
            ["git", "-C", str(source), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.splitlines()
        if not files:  # the Nix check copy has no .git
            files = [str(path.relative_to(source)) for path in source.rglob("*") if path.is_file()]
        for name in files:
            target = root / name
            if (source / name).is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source / name).read_bytes())

        assert post_edit(edit(root, "docs/index.md", "Edit"), root) is None, "a valid note passes"
        bad = root / "docs" / "hacks" / "bad.md"
        bad.write_text("# No frontmatter\n", encoding="utf-8")
        result = post_edit(edit(root, "docs/hacks/bad.md"), root)
        assert result and "missing YAML frontmatter" in result["reason"], result
        assert post_edit(edit(root, "plans/active/p.md"), root) is None, "plans are not notes"

        assert stop({}, root) is None, "no drift, no message"
        (root / ".agents" / "skills" / "rc-help" / "SKILL.md").write_text("changed\n", encoding="utf-8")
        result = stop({}, root)
        assert result and result["decision"] == "block" and "rc-help" in result["reason"], result
        assert stop({"stop_hook_active": True}, root) is None, "never loop the agent"


def check_cli() -> None:
    event = json.dumps(
        {"tool_input": {"command": 'git commit -m "Fix\n\nCo-Authored-By: Claude <noreply@anthropic.com>"'}}
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "pre-bash"], input=event.encode(), capture_output=True, check=False
    )
    assert result.returncode == 0 and json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    allowed = subprocess.run(
        [sys.executable, str(SCRIPT), "pre-bash"],
        input=b'{"tool_input": {"command": "ls"}}',
        capture_output=True,
        check=False,
    )
    assert allowed.returncode == 0 and allowed.stdout == b"", "silence lets the normal permission flow decide"
    broken = subprocess.run(
        [sys.executable, str(SCRIPT), "pre-bash"], input=b"not json", capture_output=True, check=False
    )
    assert broken.returncode == 1 and b"NOT enforced" in broken.stderr, "a broken hook warns and never blocks (exit 2)"


def check_attributed_commits(base: Path) -> None:
    repo = base / "repo"
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [*git, "commit", "-q", "--allow-empty", "-m", "Base\n\nCo-Authored-By: Claude <noreply@anthropic.com>"],
        check=True,
    )
    start = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "Clean"], check=True)
    assert rule_hooks.attributed_commits(repo, start) == [], "commits before the base are not this branch's"
    subprocess.run(
        [*git, "commit", "-q", "--allow-empty", "-m", "Feature\n\nCo-Authored-By: GPT-5 <x@openai.com>"], check=True
    )
    found = rule_hooks.attributed_commits(repo, start)
    assert len(found) == 1 and "GPT-5" in found[0], found


def test_rule_hooks() -> None:
    check_markdown_allowlist()
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        check_attribution(base)
        check_edits(base / "cc")
        check_attributed_commits(base)
    check_notes_and_drift()
    check_cli()
