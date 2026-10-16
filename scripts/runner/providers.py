#!/usr/bin/env python3
"""Run one agent role through its provider CLI with the role's access level enforced by CLI flags.

Copied from command_center_template@6489510 (scripts/council/providers.py), see
docs/decisions/0003-read-only-agents.md. RC roles never write; web and connector reading are access levels.
Runs on native Windows as well as POSIX (docs/decisions/0012-windows-native-uv.md): executables are resolved
the way the shell would (codex -> codex.cmd), and agent output is read as UTF-8 whatever the console code page.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


# Must match the role checks in scripts/validate-research-center.py.
PROVIDERS = ("claude", "codex")
ACCESS_LEVELS = ("read-only", "web-read", "connector-read")
BINARIES = {"claude": "claude", "codex": "codex"}
TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}

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

# The Claude CLI cannot list models, so these are maintained here: aliases follow the newest model
# of each tier, full ids pin one. Update when Anthropic releases models.
CLAUDE_MODELS = ["opus", "sonnet", "haiku", "claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-haiku-4-5-20251001"]


class ProviderError(RuntimeError):
    pass


def executable(name: str) -> str:
    """The path the shell would run for name. Windows does not apply PATHEXT to subprocess argv, so an npm
    launcher such as codex.cmd is only found this way; a name that is not installed is returned as is."""
    return shutil.which(name) or name


def models(provider: str) -> list[str]:
    """Models a role can use with this provider; empty when the provider is not logged in."""
    if not login_status(provider)[0]:
        return []
    if provider == "claude":
        return list(CLAUDE_MODELS)
    result = subprocess.run([executable("codex"), "debug", "models"], capture_output=True, **TEXT)
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
    if provider == "claude":
        result = subprocess.run([executable("claude"), "auth", "status"], capture_output=True, **TEXT)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False, "claude auth status returned no JSON"
        if data.get("loggedIn"):
            return True, f"logged in ({data.get('authMethod', '?')})"
        return False, "not logged in; run: claude auth login"
    result = subprocess.run([executable("codex"), "login", "status"], capture_output=True, **TEXT)
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
            # Streamed events let rc watch show what the agent is doing while it works.
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
        # On native Windows codex's read-only sandbox also blocks the commands it reads files with (probed
        # 2026-10-16 with codex-cli 0.163.0), so codex roles work only on macOS, Linux and WSL for now.
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
    raise ProviderError(f"unsupported provider: {provider}")


def run(
    role: dict[str, Any], prompt: str, cwd: Path, log: Path, timeout: int = 3600, on_say: Callable[[str], None] | None = None,
) -> str:
    """Run the role non-interactively in cwd; return its final message. The prompt goes on stdin.

    on_say receives what the agent says while it works; tool calls only go to the log.
    """
    available, detail = login_status(role["provider"])
    if not available:
        raise ProviderError(f"role {role['id']}: {role['provider']} {detail}")
    return stream_call(role, prompt, cwd, log, timeout, on_say)


def stream_call(
    role: dict[str, Any], prompt: str, cwd: Path, log: Path, timeout: int, on_say: Callable[[str], None] | None
) -> str:
    log.parent.mkdir(parents=True, exist_ok=True)
    last_message = log.with_suffix(".last.txt")
    argv = command(role, cwd, last_message)
    final = ""
    parse = {"claude": parse_claude_event, "codex": parse_codex_event}[role["provider"]]
    with log.open("w", encoding="utf-8") as stream:
        stream.write(f"$ {' '.join(argv)}\n\n")
        stream.flush()
        process = subprocess.Popen([executable(argv[0]), *argv[1:]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=stream, cwd=cwd, **TEXT)
        timer = threading.Timer(timeout, process.kill)
        timer.start()
        try:
            process.stdin.write(prompt)
            process.stdin.close()
            # Write activity as it happens: the log is what rc watch reports stalls from.
            for line in process.stdout:
                event, activity = parse(line)
                if event.get("type") == "result":
                    final = str(event.get("result", ""))
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
    return final.strip()


def message_text(event: dict[str, Any]) -> str:
    return "".join(item.get("text", "") for item in event.get("message", {}).get("content", []) if item.get("type") == "text")


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
                "Read existing.txt and quote it. Then create a file named probe.txt containing 'written' and overwrite "
                "existing.txt with 'changed', with any tool available, a shell command included. Then reply with what worked."
            )
            try:
                reply = run(role, prompt, work, work / "logs" / "probe.log", timeout=600)
            except ProviderError as error:
                reply = f"(provider error: {error})"
            wrote = (work / "probe.txt").exists() or (work / "existing.txt").read_text() != "unchanged\n"
            read = "unchanged" in reply
            print(f"{sys.argv[2]} {sys.argv[3]}: {'WROTE FILES' if wrote else 'no writes'}, {'reads' if read else 'COULD NOT READ'}; "
                  f"reply: {reply[:120]}")
            return 1 if wrote or not read else 0
    print("usage: providers.py status | models | probe <provider> <model>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
