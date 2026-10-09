#!/usr/bin/env python3
"""Run one agent role through its provider CLI with the role's access level enforced by CLI flags.

Copied from command_center_template@6489510 (scripts/council/providers.py), see
docs/decisions/0003-read-only-agents.md. RC roles never write; web and connector reading are access levels.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


# Must match the role checks in scripts/validate-research-center.py.
PROVIDERS = ("claude", "codex", "cursor")
ACCESS_LEVELS = ("read-only", "web-read", "connector-read")
BINARIES = {"claude": "claude", "codex": "codex", "cursor": "cursor-agent"}

# Claude Code: --tools is the hard set of tools the model can call, and dontAsk refuses every call that
# --allowedTools does not list. No role gets Bash, Edit or Write: the runner persists what roles return.
CLAUDE_TOOLS = {
    "read-only": ["Read", "Grep", "Glob"],
    "web-read": ["Read", "Grep", "Glob", "WebSearch", "WebFetch"],
}
# Reading tools of the user's claude.ai connectors, as headless Claude names them (probed 2026-10-09).
# Creating, updating, sharing and trashing tools are left out, so dontAsk refuses them.
CONNECTOR_TOOLS = {
    "notion": ["mcp__claude_ai_Notion__notion-search", "mcp__claude_ai_Notion__notion-fetch"],
    "gdrive": [
        "mcp__claude_ai_Google_Drive__search_files",
        "mcp__claude_ai_Google_Drive__get_file_metadata",
        "mcp__claude_ai_Google_Drive__read_file_content",
    ],
}

# Cursor: --print allows writes, and its modes only ask the model to hold back. Its permission config
# blocks tools for real, but it is read from the workspace, and a project worktree is not ours to change.
# So a Cursor role runs in a throwaway copy of the worktree that carries this config (read-only only).
CURSOR_DENY = {"permissions": {"allow": ["Read(**)"], "deny": ["Write(**)", "Shell(*)"]}}
CURSOR_MODEL = re.compile(r"^(\S+) - ")


# The Claude CLI cannot list models, so these are maintained here: aliases follow the newest model
# of each tier, full ids pin one. Update when Anthropic releases models.
CLAUDE_MODELS = ["opus", "sonnet", "haiku", "claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-haiku-4-5-20251001"]


class ProviderError(RuntimeError):
    pass


def models(provider: str) -> list[str]:
    """Models a role can use with this provider; empty when the provider is not logged in."""
    if not login_status(provider)[0]:
        return []
    if provider == "claude":
        return list(CLAUDE_MODELS)
    if provider == "cursor":
        listed = subprocess.run(["cursor-agent", "models"], capture_output=True, text=True).stdout
        return [match.group(1) for line in listed.splitlines() if (match := CURSOR_MODEL.match(line.strip()))]
    result = subprocess.run(["codex", "debug", "models"], capture_output=True, text=True)
    try:
        catalog = json.loads(result.stdout)["models"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    listed = [model for model in catalog if model.get("visibility") == "list"]
    return [model["slug"] for model in sorted(listed, key=lambda model: model.get("priority", 99))]


def login_status(provider: str) -> tuple[bool, str]:
    if provider not in BINARIES:
        return False, f"unknown provider {provider}"
    if shutil.which(BINARIES[provider]) is None:
        return False, f"{BINARIES[provider]} CLI is not installed"
    if provider == "cursor":
        result = subprocess.run(["cursor-agent", "status"], capture_output=True, text=True)
        line = next((line for line in result.stdout.splitlines() if "logged in" in line.lower()), "")
        if result.returncode == 0 and line and "not logged in" not in line.lower():
            return True, line.lstrip("✓ ").lower()
        return False, "not logged in; run: cursor-agent login"
    if provider == "claude":
        result = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False, "claude auth status returned no JSON"
        if data.get("loggedIn"):
            return True, f"logged in ({data.get('authMethod', '?')})"
        return False, "not logged in; run: claude auth login"
    result = subprocess.run(["codex", "login", "status"], capture_output=True, text=True)
    message = (result.stdout + result.stderr).strip().splitlines()
    if result.returncode == 0 and message and "logged in" in message[-1].lower():
        return True, message[-1].lower()
    return False, "not logged in; run: codex login"


def command(role: dict[str, Any], cwd: Path, last_message: Path) -> list[str]:
    provider, model, access = role["provider"], role["model"], role["access"]
    if access not in ACCESS_LEVELS:
        raise ProviderError(f"role {role.get('id')}: unknown access {access}")
    if access == "connector-read" and provider != "claude":
        raise ProviderError(f"role {role.get('id')}: only claude can read connectors")
    if provider == "claude":
        base = [
            "claude",
            "--print",
            "--model", model,
            "--permission-mode", "dontAsk",
            "--no-session-persistence",
            # Streamed events let ./rc watch show what the agent is doing while it works.
            "--output-format", "stream-json",
            "--verbose",
        ]
        if access == "connector-read":
            # The claude.ai connectors load a few seconds after start and surface through ToolSearch, which
            # --tools would hide; dontAsk with this allow-list refuses every other tool (probed 2026-10-09).
            connectors = role.get("connectors") or []
            unknown = [name for name in connectors if name not in CONNECTOR_TOOLS]
            if not connectors or unknown:
                raise ProviderError(f"role {role.get('id')}: connectors must be a non-empty subset of {sorted(CONNECTOR_TOOLS)}")
            allowed = ["Read", "Grep", "Glob", "ToolSearch"] + [tool for name in connectors for tool in CONNECTOR_TOOLS[name]]
            return [*base, "--allowedTools", *allowed]
        tools = CLAUDE_TOOLS[access]
        return [*base, "--strict-mcp-config", "--tools", *tools, "--allowedTools", *tools]
    if provider == "codex":
        return [
            # --search turns on the native web_search tool; it is a top-level flag (probed with codex-cli 0.160.1).
            "codex", *(["--search"] if access == "web-read" else []), "exec",
            "--model", model,
            "--sandbox", "read-only",
            "--cd", str(cwd),
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--color", "never",
            # JSONL events instead of the echoed prompt: the log shows commands and messages as they happen.
            "--json",
            "--output-last-message", str(last_message),
            "-",
        ]
    if provider == "cursor":
        if access != "read-only":
            raise ProviderError(f"role {role.get('id')}: cursor roles can only be read-only (no web, no connectors)")
        # No --force: shell stays off even if the permission config were missing. cwd is the snapshot.
        return [
            "cursor-agent",
            "--print",
            "--trust",
            "--workspace", str(cwd),
            "--model", model,
            "--output-format", "stream-json",
        ]
    raise ProviderError(f"unsupported provider: {provider}")


def snapshot(worktree: Path) -> tuple[Path, dict[str, tuple[int, int]]]:
    """A throwaway copy of what Git would commit in the worktree, with Cursor's deny config, and a
    fingerprint of every file in it, so a write that slips through is detected afterwards."""
    directory = Path(tempfile.mkdtemp(prefix="cc-cursor-"))
    listed = subprocess.run(
        ["git", "-C", str(worktree), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True,
    )
    names = listed.stdout.split("\0") if listed.returncode == 0 else [
        str(path.relative_to(worktree)) for path in worktree.rglob("*") if path.is_file()
    ]
    for name in filter(None, names):
        source = worktree / name
        if source.is_file() and not source.is_symlink():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    config = directory / ".cursor" / "cli.json"  # replaces a project's own config in the copy
    config.parent.mkdir(exist_ok=True)
    config.write_text(json.dumps(CURSOR_DENY), encoding="utf-8")
    return directory, fingerprint(directory)


def fingerprint(directory: Path) -> dict[str, tuple[int, int]]:
    return {
        str(path.relative_to(directory)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in directory.rglob("*")
        if path.is_file()
    }


def run(
    role: dict[str, Any], prompt: str, cwd: Path, log: Path, timeout: int = 3600, on_say: Callable[[str], None] | None = None,
    shared: Path | None = None,
) -> str:
    """Run the role non-interactively in cwd; return its final message. The prompt goes on stdin.

    on_say receives what the agent says while it works; tool calls only go to the log.
    shared: a snapshot() of cwd owned by the caller, for many Cursor calls on one worktree. The caller
    then compares its fingerprint once after the last call and removes it.
    """
    available, detail = login_status(role["provider"])
    if not available:
        raise ProviderError(f"role {role['id']}: {role['provider']} {detail}")
    if role["provider"] != "cursor":
        return stream_call(role, prompt, cwd, log, timeout, on_say)
    if shared is not None:
        return stream_call(role, prompt, shared, log, timeout, on_say)
    workspace, before = snapshot(cwd)
    try:
        reply = stream_call(role, prompt, workspace, log, timeout, on_say)
        # Fail closed: a write that got past the permission config voids the reply.
        if fingerprint(workspace) != before:
            raise ProviderError(f"role {role['id']} (cursor {role['model']}) changed its read-only snapshot; see {log}")
        return reply
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def stream_call(
    role: dict[str, Any], prompt: str, cwd: Path, log: Path, timeout: int, on_say: Callable[[str], None] | None
) -> str:
    log.parent.mkdir(parents=True, exist_ok=True)
    last_message = log.with_suffix(".last.txt")
    argv = command(role, cwd, last_message)
    final = ""
    parse = {"claude": parse_claude_event, "codex": parse_codex_event, "cursor": parse_cursor_event}[role["provider"]]
    # Cursor's result joins every message, preambles included; the reply is what it said after its last tool call.
    closing: list[str] = []
    with log.open("w", encoding="utf-8") as stream:
        stream.write(f"$ {' '.join(argv)}\n\n")
        stream.flush()
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stream, cwd=cwd, text=True)
        timer = threading.Timer(timeout, process.kill)
        timer.start()
        try:
            process.stdin.write(prompt)
            process.stdin.close()
            # Write activity as it happens: the log is what ./rc watch reports stalls from.
            for line in process.stdout:
                event, activity = parse(line)
                if event.get("type") == "result":
                    final = str(event.get("result", ""))
                elif event.get("type") == "tool_call":
                    closing = []
                elif event.get("type") == "assistant":
                    closing.append(message_text(event))
                if on_say:
                    for said in activity.splitlines():
                        if said.startswith("say: "):
                            on_say(said[5:])
                stream.write(f"{activity}\n" if activity else "")
                stream.flush()
            process.wait()
        finally:
            timer.cancel()
    if process.returncode != 0:
        raise ProviderError(f"role {role['id']} ({role['provider']} {role['model']}) failed; see {log}")
    if role["provider"] == "codex":
        return last_message.read_text(encoding="utf-8").strip()
    if role["provider"] == "cursor":
        return "\n\n".join(text for text in closing if text.strip()).strip() or final.strip()
    return final.strip()


def message_text(event: dict[str, Any]) -> str:
    return "".join(item.get("text", "") for item in event.get("message", {}).get("content", []) if item.get("type") == "text")


def parse_cursor_event(line: str) -> tuple[dict[str, Any], str]:
    """One `cursor-agent --print --output-format stream-json` line: the event, and a short activity line."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return {}, line.strip()
    kind = event.get("type")
    if kind == "result":
        return event, f"result: {event.get('subtype', 'done')}"
    if kind == "tool_call" and event.get("subtype") == "started":
        call = event.get("tool_call", {})
        name = next((key for key in call if key.endswith("ToolCall")), "tool")
        arguments = call.get(name, {}).get("args", {})
        target = next((str(arguments[key]) for key in ("path", "command", "pattern", "globPattern") if key in arguments), "")
        return event, f"tool: {name.removesuffix('ToolCall')} {target}".strip()[:200]
    if kind == "assistant" and message_text(event).strip():
        return event, "say: " + " ".join(message_text(event).split())[:160]
    return event, ""


def parse_claude_event(line: str) -> tuple[dict[str, Any], str]:
    """One stream-json line of `claude --print`: the event, and a short activity line for the log."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return {}, line.strip()
    if event.get("type") == "result":
        return event, f"result: {event.get('subtype', 'done')}"
    if event.get("type") != "assistant":
        return event, ""
    activity = []
    for item in event.get("message", {}).get("content", []):
        if item.get("type") == "tool_use":
            arguments = item.get("input", {})
            target = next((str(arguments[key]) for key in ("file_path", "pattern", "path", "command") if key in arguments), "")
            activity.append(f"tool: {item.get('name')} {target}".strip())
        elif item.get("type") == "text" and item.get("text", "").strip():
            activity.append("say: " + " ".join(item["text"].split())[:160])
    return event, "\n".join(activity)


def parse_codex_event(line: str) -> tuple[dict[str, Any], str]:
    """One `codex exec --json` line: the event, and a short activity line for the log."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return {}, line.strip()
    item = event.get("item", {})
    if event.get("type") == "item.started" and item.get("type") == "command_execution":
        return event, f"tool: {item.get('command', '')}"[:200]
    if event.get("type") == "item.completed" and item.get("type") == "agent_message" and item.get("text", "").strip():
        return event, "say: " + " ".join(item["text"].split())[:160]
    if event.get("type") in {"turn.failed", "error"}:
        return event, f"error: {event.get('error') or event.get('message', '')}"[:200]
    if event.get("type") == "turn.completed":
        return event, "result: success"
    return event, ""


def main() -> int:
    """`status`: print every provider's login state. `probe <provider> <model>`: prove read-only holds."""
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "models":
        print(json.dumps({provider: models(provider) for provider in PROVIDERS}))
        return 0
    if action == "status":
        for provider in PROVIDERS:
            available, detail = login_status(provider)
            print(f"{provider}: {'ok' if available else 'MISSING'} - {detail}")
        return 0
    if action == "probe" and len(sys.argv) == 4:
        role = {"id": "probe", "provider": sys.argv[2], "model": sys.argv[3], "access": "read-only"}
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "existing.txt").write_text("unchanged\n", encoding="utf-8")
            prompt = (
                "Create a file named probe.txt containing 'written' and overwrite existing.txt with "
                "'changed'. Use any tool available. Then reply with exactly DONE or BLOCKED."
            )
            try:
                reply = run(role, prompt, work, work / "logs" / "probe.log", timeout=600)
            except ProviderError as error:
                reply = f"(provider error: {error})"
            # A Cursor role works in a snapshot: a write there surfaces as the snapshot error.
            wrote = (work / "probe.txt").exists() or (work / "existing.txt").read_text() != "unchanged\n" \
                or "changed its read-only snapshot" in reply
            print(f"{sys.argv[2]} {sys.argv[3]} read-only: {'WROTE FILES' if wrote else 'no writes'}; reply: {reply[:120]}")
            return 1 if wrote else 0
    print("usage: providers.py status | models | probe <provider> <model>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
