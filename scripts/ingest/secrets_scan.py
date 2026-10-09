#!/usr/bin/env python3
"""Find and redact secrets in text before it is committed (docs/decisions/0002-committed-extracted-sources.md).

`redact` replaces each value with [REDACTED:<kind>] and reports kind and line, never the value.
`secrets_scan.py <root> <dir>...` fails when a known pattern is left anywhere under the given folders.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# (kind, pattern, group holding the secret value). Specific token formats first; the generic
# assignment patterns only fire on a value that looks like a credential, not on prose.
PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL), 0),
    ("aws-access-key", re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"), 1),
    ("github-token", re.compile(r"\b((?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b"), 1),
    ("slack-token", re.compile(r"\b(xox[abposr]-[A-Za-z0-9-]{10,})\b"), 1),
    ("anthropic-key", re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{20,})"), 1),
    ("openai-key", re.compile(r"\b(sk-(?:proj-)?[A-Za-z0-9_-]{32,})"), 1),
    ("google-api-key", re.compile(r"\b(AIza[0-9A-Za-z_-]{35})\b"), 1),
    ("stripe-key", re.compile(r"\b((?:sk|rk)_live_[0-9A-Za-z]{20,})\b"), 1),
    ("jwt", re.compile(r"\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"), 1),
    ("url-credentials", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s@/]{3,})@[^\s]+", re.IGNORECASE), 1),
    (
        "assigned-secret",
        re.compile(
            r"""(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|client[_-]?secret|token)\b"""
            r"""\s*[:=]\s*["']?([^\s"'`,;]{8,})["']?"""
        ),
        1,
    ),
]

MARKER = re.compile(r"\[REDACTED:[a-z-]+\]")
# Values that name a placeholder rather than hold a secret.
PLACEHOLDER = re.compile(r"(?i)^(?:\$\{?[A-Z_]+\}?|<[^>]+>|x{4,}|\*{4,}|changeme|example\w*|your[_-]?\w+|placeholder|redacted\w*|\[REDACTED.*|null|none|true|false|process\.env\.\w+|os\.environ.*|env\(.*)$")


def looks_secret(kind: str, value: str) -> bool:
    if MARKER.search(value) or PLACEHOLDER.match(value):
        return False
    if kind == "assigned-secret":
        # Code assigns calls and attributes (token = get_token(), key = self.api_key): not values.
        if re.search(r"[()\[\]{}<>]", value) or re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", value):
            return False
        # A credential mixes character classes; plain words and identifiers are prose or code.
        classes = sum(bool(re.search(pattern, value)) for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
        return classes >= 3 or (classes >= 2 and len(value) >= 20 and not value.isidentifier())
    return True


def find(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern, group in PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(group)
            if any(start < other_end and other_start < end for other_start, other_end in taken):
                continue
            if not looks_secret(kind, match.group(group)):
                continue
            taken.append((start, end))
            found.append({"kind": kind, "start": start, "end": end, "line": text.count("\n", 0, start) + 1})
    return sorted(found, key=lambda item: item["start"])


def redact(text: str) -> tuple[str, list[dict[str, Any]]]:
    """The text with every secret replaced, and what was replaced (kind and line only)."""
    found = find(text)
    for item in reversed(found):
        text = text[: item["start"]] + f"[REDACTED:{item['kind']}]" + text[item["end"]:]
    return text, [{"kind": item["kind"], "line": item["line"]} for item in found]


def scan(root: Path, folders: list[str]) -> list[str]:
    problems = []
    for folder in folders:
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for item in find(text):
                problems.append(f"{path.relative_to(root).as_posix()}:{item['line']}: unredacted {item['kind']}")
    return problems


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: secrets_scan.py <root> <folder>...", file=sys.stderr)
        return 2
    problems = scan(Path(sys.argv[1]), sys.argv[2:])
    if problems:
        print("secret scan failed (redact the values, then re-run ./rc check):", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"secret scan passed: {', '.join(sys.argv[2:])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
