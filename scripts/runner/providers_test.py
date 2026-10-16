#!/usr/bin/env python3
"""Test the providers with fake claude and codex CLIs that run on Windows (as .cmd launchers) and POSIX alike:
access levels map to read-only CLI flags, executables resolve the way the shell would, login state is read,
streamed events become the reply and the log, agent output is decoded as UTF-8, and a failing CLI raises."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import providers  # noqa: E402

# The fake answers `auth status` / `login status`, and in --print / exec mode streams events like the real CLI.
FAKE = '''import json, os, sys
name, args = sys.argv[1], sys.argv[2:]
logged_in = os.environ.get("FAKE_LOGIN") == "1"
if args[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": logged_in, "authMethod": "claude.ai"}))
    sys.exit(0)
if args[:2] == ["login", "status"]:
    print("Logged in using ChatGPT" if logged_in else "Not logged in")
    sys.exit(0 if logged_in else 1)
prompt = sys.stdin.buffer.read().decode("utf-8")  # as the real CLIs do, whatever the console code page
Path = __import__("pathlib").Path
Path(os.environ["FAKE_SEEN"]).write_text(json.dumps({"args": args, "prompt": prompt}), encoding="utf-8")
if os.environ.get("FAKE_FAIL"):
    sys.exit(3)
out = sys.stdout.buffer
def emit(event):
    out.write((json.dumps(event, ensure_ascii=False) + "\\n").encode("utf-8"))
if name == "claude":
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "brief.md"}}]}})
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "調査を始めます"}]}})
    emit({"type": "result", "subtype": "success", "result": "答え: 週4日勤務 DONE"})
else:
    emit({"type": "item.completed", "item": {"type": "agent_message", "text": "reading"}})
    Path(args[args.index("--output-last-message") + 1]).write_text("codex answer", encoding="utf-8")
    emit({"type": "turn.completed"})
'''


def install_fake(bin_dir: Path, name: str) -> None:
    """A fake CLI on PATH: name.cmd on Windows, an executable script elsewhere."""
    script = bin_dir / "fake_cli.py"
    script.write_text(FAKE, encoding="utf-8")
    if os.name == "nt":
        (bin_dir / f"{name}.cmd").write_text(f'@"{sys.executable}" "{script}" {name} %*\r\n', encoding="utf-8")
    else:
        launcher = bin_dir / name
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" {name} "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)


def refused(role: dict) -> bool:
    try:
        providers.command(role, Path("."), Path("last.txt"))
    except providers.ProviderError:
        return True
    return False


def after(argv: list[str], flag: str) -> list[str]:
    """The values of a variadic flag: everything up to the next flag."""
    values = []
    for item in argv[argv.index(flag) + 1:]:
        if item.startswith("--"):
            break
        values.append(item)
    return values


def check_access_flags() -> None:
    """Every access level maps to CLI flags that refuse writing; web and connectors only where asked."""
    claude = {"id": "r", "provider": "claude", "model": "sonnet"}
    argv = providers.command({**claude, "access": "read-only"}, Path("."), Path("last.txt"))
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert after(argv, "--tools") == ["Read", "Grep", "Glob"] == after(argv, "--allowedTools"), argv
    assert "--strict-mcp-config" in argv, "no connectors for a read-only role"

    argv = providers.command({**claude, "access": "web-read"}, Path("."), Path("last.txt"))
    assert "WebSearch" in after(argv, "--tools") and "WebFetch" in after(argv, "--allowedTools")
    assert not {"Write", "Edit", "Bash"} & set(after(argv, "--tools")), argv

    argv = providers.command({**claude, "access": "connector-read", "connectors": ["notion"]}, Path("."), Path("last.txt"))
    allowed = after(argv, "--allowedTools")
    assert "--tools" not in argv and "--strict-mcp-config" not in argv, "connectors surface through ToolSearch"
    assert "mcp__claude_ai_Notion__notion-fetch" in allowed and not any("Drive" in tool for tool in allowed), allowed
    assert not any(word in tool for tool in allowed for word in ("create", "update", "trash", "share", "Write", "Bash"))
    assert refused({**claude, "access": "connector-read"}), "connector-read needs connectors"
    assert refused({**claude, "access": "connector-read", "connectors": ["slack"]}), "unknown connector"
    assert refused({**claude, "access": "write-worktree"}), "RC roles never write"

    codex = {"id": "g", "provider": "codex", "model": "gpt"}
    argv = providers.command({**codex, "access": "web-read"}, Path("."), Path("last.txt"))
    assert argv[:3] == ["codex", "--search", "exec"] and argv[argv.index("--sandbox") + 1] == "read-only", argv
    argv = providers.command({**codex, "access": "read-only"}, Path("."), Path("last.txt"))
    assert "--search" not in argv and argv[argv.index("--sandbox") + 1] == "read-only"
    assert refused({**codex, "access": "connector-read", "connectors": ["notion"]})
    assert refused({"id": "j", "provider": "cursor", "model": "grok", "access": "read-only"}), "cursor support is gone"


def main() -> int:
    check_access_flags()
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        for name in ("claude", "codex"):
            install_fake(bin_dir, name)
        seen = base / "seen.json"
        os.environ.update({"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_SEEN": str(seen)})
        os.environ.pop("FAKE_LOGIN", None)

        resolved = Path(providers.executable("codex"))
        assert resolved.parent == bin_dir, f"codex resolves to the launcher on PATH, .cmd on Windows: {resolved}"
        assert providers.executable("no-such-cli") == "no-such-cli"

        assert providers.login_status("claude") == (False, "not logged in; run: claude auth login")
        assert providers.login_status("codex") == (False, "not logged in; run: codex login")
        assert providers.models("claude") == [], "no models while logged out"
        assert providers.login_status("cursor") == (False, "unknown provider cursor")
        os.environ["FAKE_LOGIN"] = "1"
        assert providers.login_status("claude") == (True, "logged in (claude.ai)")
        assert providers.login_status("codex")[0]

        work = base / "work"
        work.mkdir()
        said: list[str] = []
        role = {"id": "analyst", "provider": "claude", "model": "opus", "access": "read-only"}
        reply = providers.run(role, "プロンプト: 調べて", work, base / "logs" / "analyst.log", timeout=60, on_say=said.append)
        assert reply == "答え: 週4日勤務 DONE", f"UTF-8 survives the console code page: {reply!r}"
        assert said == ["調査を始めます"], said
        log = (base / "logs" / "analyst.log").read_text(encoding="utf-8")
        assert "tool: Read brief.md" in log and "say: 調査を始めます" in log, log
        import json
        assert json.loads(seen.read_text(encoding="utf-8"))["prompt"] == "プロンプト: 調べて", "the prompt reaches stdin as UTF-8"

        codex = {"id": "researcher", "provider": "codex", "model": "gpt", "access": "web-read"}
        assert providers.run(codex, "go", work, base / "logs" / "codex.log", timeout=60) == "codex answer"

        os.environ["FAKE_FAIL"] = "1"
        try:
            providers.run(role, "go", work, base / "logs" / "fail.log", timeout=60)
            raise AssertionError("a failing CLI must raise")
        except providers.ProviderError as error:
            assert "failed; see" in str(error)
        os.environ.pop("FAKE_FAIL")
    print("providers test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
