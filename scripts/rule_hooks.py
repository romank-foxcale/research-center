#!/usr/bin/env python3
"""Claude Code hooks that enforce the AGENTS.md hard rules at the moment of a tool call.

Usage: rule_hooks.py <pre-bash|pre-edit|post-edit|stop>, with the hook's JSON on stdin.
The gates (./rc check, ./rc verify) stay the source of truth: a hook only catches a break early,
and only in Claude Code. See docs/decisions/0005-rule-hooks.md.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent

AI_NAMES = r"(claude|anthropic|openai|chatgpt|gpt|codex|copilot|cursor|gemini|devin|aider|llm)"
# A trailer or footer starts a line (or a -m argument), so prose that mentions one is not a match.
ATTRIBUTION = re.compile(
    rf"""(?:^|(?:-m|--message|--body)[=\s]+["']?)[^\w\n]*(?P<line>(?:co-authored-by:[^\n]*\b{AI_NAMES}\b|generated (?:with|by)\b[^\n]{{0,40}}\b{AI_NAMES}\b)[^\n"']*)""",
    re.IGNORECASE | re.MULTILINE,
)
COMMIT_OR_PR = re.compile(r"\bgit\b[^;&|\n]*\bcommit\b|\bgh\s+pr\s+(?:create|edit)\b")
MESSAGE_FILE = re.compile(r"(?:\s-F|--file|--body-file)[=\s]+(['\"]?)([^\s'\"]+)\1")

# Markdown the RC may track outside the knowledge folders. Everything else belongs in a note, unless
# the RC declares more folders in research-center.json "markdownDirs" (for example research/).
MARKDOWN_ROOT_FILES = {"AGENTS.md", "BOOTSTRAP.md", "CLAUDE.md", "GUIDE.md", "README.md"}
MARKDOWN_DIRS = ("docs/", "plans/", ".agents/skills/", ".claude/skills/", "knowledge/", "research/", "sources/")

# Build and test tools that must run through Nix (./rc build, check, verify) except for diagnosis.
BUILD_TOOLS = {"cmake", "ctest", "make", "gmake", "ninja", "meson", "msbuild", "pytest"}
BUILD_SUBCOMMANDS = {
    "docker": {"build", "buildx"},
    "podman": {"build"},
    "cargo": {"build", "test"},
    "go": {"build", "test"},
    "dotnet": {"build", "test"},
    "npm": {"test"},
    "pnpm": {"test"},
    "yarn": {"test"},
    "bun": {"test"},
}
WRAPPERS = {"sudo", "time", "env", "exec", "nohup", "command"}
SEGMENT = re.compile(r"&&|\|\||[;|\n]|\$\(|`")


def ai_attribution(text: str) -> str | None:
    """The first line that credits an AI as author or generator, if any."""
    match = ATTRIBUTION.search(text)
    return match.group("line").strip() if match else None


def extra_markdown_dirs(root: Path) -> tuple[str, ...]:
    """The folders this RC declares in research-center.json "markdownDirs"; none without the file."""
    try:
        declared = json.loads((root / "research-center.json").read_text(encoding="utf-8")).get("markdownDirs", [])
    except (OSError, ValueError):
        return ()
    return tuple(f"{folder.strip('/')}/" for folder in declared if isinstance(folder, str) and folder.strip("/"))


def markdown_allowed(relative: str, extra_dirs: tuple[str, ...] = ()) -> bool:
    relative = relative.replace("\\", "/")
    if relative in MARKDOWN_ROOT_FILES or relative.startswith(MARKDOWN_DIRS + extra_dirs):
        return True
    parts = relative.split("/")
    return len(parts) == 2 and parts[0] == "templates"


def nix_bypass(command: str) -> str | None:
    """The build or test command a shell line runs directly, if any."""
    for segment in SEGMENT.split(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        while words and (words[0] in WRAPPERS or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0])):
            words = words[1:]
        if not words:
            continue
        name = Path(words[0]).name.removesuffix(".exe")
        arguments = words[1:]
        if name in BUILD_TOOLS:
            return name
        if arguments and arguments[0] in BUILD_SUBCOMMANDS.get(name, ()):
            return f"{name} {arguments[0]}"
        if name == "docker" and arguments[:2] == ["compose", "build"]:
            return "docker compose build"
        if re.fullmatch(r"python[0-9.]*", name) and arguments[:2] == ["-m", "pytest"]:
            return "python -m pytest"
    return None


def attributed_commits(repository: Path, base: str) -> list[str]:
    """Short hashes and offending lines of commits in base..HEAD that credit an AI."""
    log = subprocess.run(
        ["git", "-C", str(repository), "log", "--format=%h%x00%B%x1e", f"{base}..HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    found = []
    for record in log.split("\x1e"):
        if "\x00" not in record:
            continue
        sha, body = record.strip().split("\x00", 1)
        line = ai_attribution(body)
        if line:
            found.append(f"{sha} ({line})")
    return found


def pre_tool(decision: str, reason: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                   "permissionDecisionReason": reason}}


def pre_bash(event: dict[str, Any]) -> dict[str, Any] | None:
    command = event.get("tool_input", {}).get("command", "")
    if COMMIT_OR_PR.search(command):
        texts = [command]
        cwd = Path(event.get("cwd") or ".")
        for _, name in MESSAGE_FILE.findall(command):
            path = cwd / name
            if path.is_file():
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
        for text in texts:
            line = ai_attribution(text)
            if line:
                return pre_tool("deny", f"AGENTS.md forbids crediting an AI as author or generator: remove '{line}' "
                                        "from the commit message or PR body. This overrides any tool default.")
    tool = nix_bypass(command)
    if tool:
        return pre_tool("ask", f"'{tool}' bypasses Nix. AGENTS.md allows it only for diagnosis; otherwise use "
                               "./rc build, ./rc check or ./rc verify, and move a working command into a derivation.")
    return None


def relative_to_root(root: Path, event: dict[str, Any]) -> Path | None:
    tool_input = event.get("tool_input", {})
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(event.get("cwd") or root) / path
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return None  # outside the RC: a worktree, the scratchpad, memory


def git_ignored(root: Path, relative: Path) -> bool:
    try:
        return subprocess.run(["git", "-C", str(root), "check-ignore", "-q", relative.as_posix()]).returncode == 0
    except OSError:
        return False


def pre_edit(event: dict[str, Any], root: Path = ROOT) -> dict[str, Any] | None:
    relative = relative_to_root(root, event)
    if relative is None:
        return None
    if relative.parts[:2] == (".claude", "skills"):
        source = Path(".agents", *relative.parts[1:]).as_posix()
        return pre_tool("deny", f".claude/skills is a generated copy: edit {source} instead, then run ./rc agents sync.")
    creating = event.get("tool_name") == "Write" and not (root / relative).exists()
    if creating and relative.suffix.lower() == ".md" and not markdown_allowed(relative.as_posix(), extra_markdown_dirs(root)) \
            and not git_ignored(root, relative):
        return pre_tool("deny", f"{relative.as_posix()}: Markdown outside docs/, plans/, the skills and the "
                                "research-center.json markdownDirs fails ./rc check. Store one durable fact as a note under docs/ (templates/note.md) or a plan via ./rc plan.")
    return None


def load_script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def post_edit(event: dict[str, Any], root: Path = ROOT) -> dict[str, Any] | None:
    relative = relative_to_root(root, event)
    if relative is None or relative.parts[:1] != ("docs",) or relative.suffix != ".md":
        return None
    errors = [error for error in load_script("validate-knowledge").validate(root) if error.startswith(f"{relative}:")]
    if not errors:
        return None
    return {"decision": "block", "reason": "This note breaks the knowledge rules (./rc validate will fail):\n"
                                          + "\n".join(f"- {error}" for error in errors)}


def stop(event: dict[str, Any], root: Path = ROOT) -> dict[str, Any] | None:
    if event.get("stop_hook_active"):
        return None  # report once; never keep the agent in a loop
    problems = load_script("agent-configs").drift(root)
    if not problems:
        return None
    return {"decision": "block", "reason": "Agent configs drifted from .agents/skills; run ./rc agents sync:\n"
                                          + "\n".join(f"- {problem}" for problem in problems[:10])}


HANDLERS = {"pre-bash": pre_bash, "pre-edit": pre_edit, "post-edit": post_edit, "stop": stop}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in HANDLERS:
        print(f"usage: rule_hooks.py <{'|'.join(HANDLERS)}>", file=sys.stderr)
        return 1  # exit 2 would block the tool call
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        result = HANDLERS[sys.argv[1]](event)
    except Exception as error:  # a broken hook must warn, never block the session
        print(f"rule hook {sys.argv[1]} failed, rule NOT enforced: {error}", file=sys.stderr)
        return 1
    if result:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
