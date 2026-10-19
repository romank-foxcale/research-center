"""Shared runtime of ./rc ingest and ./rc research: instance settings, roles, the call budget, agent calls
with one validated retry, and the event stream. Agents never write: every file is written here, by the runner,
after secrets are redacted (docs/decisions/0003-read-only-agents.md)."""

from __future__ import annotations

import concurrent.futures
import datetime
import hashlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "ingest"))
import events  # noqa: E402
import providers  # noqa: E402
import secrets_scan  # noqa: E402

SETTINGS = "research-center.json"
TIMEOUT = 2400


class RcError(RuntimeError):
    pass


class BudgetExceeded(RcError):
    pass


# What a check raises on a reply that is malformed rather than wrong: a retry can fix both.
REJECTED = (ValueError, TypeError, AttributeError, KeyError)


def describe(error: BaseException) -> str:
    return str(error) if isinstance(error, ValueError) else f"malformed reply ({type(error).__name__}: {error})"


def today() -> str:
    return datetime.date.today().isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    replace(temporary, path)


# On Windows a rename onto a file fails with "Access is denied" while any other process has that file open, even
# one that shares delete as an antivirus scan or the search indexer does right after a write. Such holds last
# milliseconds, so the rename is retried for a few seconds before the error counts.
REPLACE_WAITS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0) if os.name == "nt" else ()


def replace(source: Path, target: Path) -> None:
    for wait in REPLACE_WAITS:
        try:
            source.replace(target)
            return
        except PermissionError:
            time.sleep(wait)
    source.replace(target)


def write_text(path: Path, text: str) -> list[dict[str, Any]]:
    """Write text the runner produced, secrets redacted first; return what was redacted."""
    clean, found = secrets_scan.redact(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(clean if clean.endswith("\n") else clean + "\n", encoding="utf-8", newline="\n")
    return found


def instance(path: Path) -> Path:
    """The instance a data root belongs to: the nearest folder upward with research-center.json. A profile
    (profiles/<id>/) is a data root inside its instance; settings, roles, adapters, templates and skills are the
    instance's (docs/decisions/0015-profiles.md). Without one, the path itself (the template)."""
    for candidate in (path, *path.parents):
        if (candidate / SETTINGS).is_file():
            return candidate
    return path


def settings(root: Path) -> dict[str, Any]:
    path = instance(root) / SETTINGS
    if not path.is_file():
        raise RcError(f"{SETTINGS} is missing: this is the template, not an instance; create one with rc-kit new <name> (or ./rc bootstrap install <dir>)")
    return load_json(path)


def role(root: Path, identifier: str) -> dict[str, Any]:
    path = instance(root) / "catalog" / "agents" / f"{identifier}.json"
    if not path.is_file():
        raise RcError(f"role {identifier}: catalog/agents/{identifier}.json is missing")
    return load_json(path)


def skill_text(root: Path, name: str) -> str:
    text = (instance(root) / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL).strip()


FENCE = re.compile(r"^(`{3,})\s*(\S*)\s*$")


def fenced_blocks(reply: str) -> list[tuple[str, str]]:
    """Every fenced block of a reply as (language, body). A fence closes only on a bare fence of at least the
    opening length, so a ```python block before the ```json one does not shift the pairing."""
    blocks: list[tuple[str, str]] = []
    opening, language, body = "", "", []
    for line in reply.splitlines():
        match = FENCE.match(line.strip())
        if not opening:
            if match:
                opening, language, body = match.group(1), match.group(2).lower(), []
        elif match and not match.group(2) and len(match.group(1)) >= len(opening):
            blocks.append((language, "\n".join(body)))
            opening = ""
        else:
            body.append(line)
    return blocks


def extract_json(reply: str) -> Any:
    """The last parseable fenced ```json block of a reply, else the last parseable untagged block, else the whole
    reply when it is bare JSON."""
    blocks = fenced_blocks(reply)
    tagged = [body for language, body in blocks if language == "json"]
    untagged = [body for language, body in blocks if not language]
    for candidate in [*reversed(tagged), *reversed(untagged)]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(reply.strip())
    except json.JSONDecodeError as error:
        raise ValueError("the reply holds no parseable JSON block") from error


class Session:
    """One ./rc run: an event stream, per-call logs, and a budget of agent calls shared by every stage."""

    def __init__(self, root: Path, name: str, budget: int):
        self.root = root
        self.events, self.owns = events.own_stream(root, name)
        self.logs = self.events.path.parent / "logs"
        self.budget = budget
        self.calls = 0
        self.lock = threading.Lock()
        self.active: dict[str, Path] = {}
        self.watchdog = events.Watchdog(self.events, self.activity)
        # Where call_checked keeps accepted replies so a failed or interrupted stage resumes per call; None keeps nothing.
        self.replies: Path | None = None

    def activity(self) -> dict[str, tuple[float, str]]:
        with self.lock:
            return {who: events.file_activity(log) for who, log in self.active.items()}

    def __enter__(self) -> "Session":
        self.events.emit("start", f"{self.events.path.parent.name} (budget {self.budget} agent calls)", pid=os.getpid())
        self.watchdog.start()
        return self

    def __exit__(self, kind: type | None, error: BaseException | None, _: object) -> None:
        self.watchdog.stopped.set()
        if error is not None:
            self.events.emit("error", f"{kind.__name__}: {error}")
        if self.owns:
            self.events.emit(events.END, "done" if error is None else "failed", ok=error is None, calls=self.calls)

    def say(self, text: str, kind: str = "step") -> None:
        self.events.emit(kind, text)
        print(text, flush=True)

    def reserve(self, label: str) -> None:
        with self.lock:
            if self.calls >= self.budget:
                raise BudgetExceeded(
                    f"agent call budget of {self.budget} reached before {label}; finished work is kept, "
                    "re-run to resume or pass --budget"
                )
            self.calls += 1

    def call(self, role_id: str, body: str, label: str) -> str:
        """Run one role on a prompt; the role's skills come first. The reply is returned, never trusted."""
        self.reserve(label)
        spec = role(self.root, role_id)
        skills = "\n\n".join(skill_text(self.root, name) for name in spec.get("skills", []))
        # Named outright: in a profile the current directory is profiles/<id>/, not the repository root, and an
        # agent that guesses the root reads the wrong paths first.
        prompt = (f"{skills}\n\n# Context\n\nThe current directory is {self.root}. Every relative path in this task is "
                  f"relative to it. You can read files; you cannot write any.\n\n{body}")
        log = self.logs / f"{label}.log"
        with self.lock:
            self.active[f"{label} ({spec['provider']} {spec['model']})"] = log
        self.events.emit("agent", f"{label}: {spec['provider']} {spec['model']} started")
        started = time.time()
        try:
            reply = providers.run(spec, prompt, self.root, log, timeout=TIMEOUT,
                                  on_say=lambda text: self.events.emit("say", f"{label}: {text}"))
        finally:
            with self.lock:
                self.active = {who: path for who, path in self.active.items() if path != log}
        self.events.emit("agent", f"{label}: answered in {events.clock(int(time.time() - started))}")
        return reply

    def call_checked(self, role_id: str, body: str, label: str, check: Callable[[str], Any]) -> Any:
        """call(), then check(reply); a reply that fails the check gets one retry with the problems listed.

        A wrong shape (a list where an object was asked, a missing key) is a rejected reply like any other.
        With self.replies set, an accepted reply is kept there at once and reused by a later run with the same
        prompt, so a sibling's failure or an interruption never costs a paid call twice."""
        cache = self.replies / f"{label}.json" if self.replies else None
        digest = hashlib.sha256(f"{role_id}\n{body}".encode()).hexdigest()
        if cache and cache.is_file():
            kept = load_json(cache)
            if kept.get("prompt") == digest:
                try:
                    result = check(kept["reply"])
                    self.events.emit("agent", f"{label}: reusing the accepted reply of an earlier run")
                    return result
                except REJECTED:
                    pass  # the checks changed since; ask again
        reply = self.call(role_id, body, label)
        try:
            result = check(reply)
        except REJECTED as error:
            problem = describe(error)
            self.events.emit("warn", f"{label}: reply rejected ({problem}); retrying once")
            retry = (
                f"{body}\n\n# Your previous reply was rejected\n\n{problem}\n\n"
                f"Previous reply:\n\n{reply[:20000]}\n\nAnswer again, fixing exactly these problems."
            )
            reply = self.call(role_id, retry, f"{label}-retry")
            try:
                result = check(reply)
            except REJECTED as error:
                raise ValueError(f"{label}: reply rejected twice: {describe(error)}") from error
        if cache:
            write_json(cache, {"prompt": digest, "reply": reply})
        return result

    def parallel(self, jobs: list[tuple[str, Callable[[], Any]]], workers: int = 4) -> dict[str, Any]:
        """Run labelled jobs at once; the first failure is raised after every job ended. Jobs that finished
        keep their accepted replies through call_checked, so a re-run repeats only the failed ones."""
        results: dict[str, Any] = {}
        errors: list[BaseException] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(job): label for label, job in jobs}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results[futures[future]] = future.result()
                except BaseException as error:  # noqa: BLE001 - reported below
                    errors.append(error)
        if errors:
            raise errors[0]
        return results
