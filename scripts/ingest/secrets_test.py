#!/usr/bin/env python3
"""Test secret redaction: each token format is caught, values never reach the report, and code or prose
that only looks like an assignment is left alone."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import secrets_scan

# Built from parts so this file itself never holds a full token pattern.
GITHUB = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
ANTHROPIC = "sk-ant-" + "api03-abcdefghijklmnopqrstuvwx_YZ0123"
AWS = "AKIA" + "IOSFODNN7EXAMPLE"
SLACK = "xoxb-" + "1234567890-abcdefghijkl"
KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----"


def test_secrets() -> None:
    for kind, value in (
        ("github-token", GITHUB),
        ("anthropic-key", ANTHROPIC),
        ("aws-access-key", AWS),
        ("slack-token", SLACK),
    ):
        text, found = secrets_scan.redact(f"token in prose: {value} end")
        assert value not in text and f"[REDACTED:{kind}]" in text, (kind, text)
        assert found == [{"kind": kind, "line": 1}], found

    text, found = secrets_scan.redact(f"line one\n{KEY}\nafter")
    assert "MIIEow" not in text and found == [{"kind": "private-key", "line": 2}], (text, found)

    text, found = secrets_scan.redact("DATABASE_URL=postgres://app:S3cr3tPass@db.internal:5432/app")
    assert "S3cr3tPass" not in text and found[0]["kind"] == "url-credentials", (text, found)

    text, found = secrets_scan.redact('password: "Hunter2-xyz!9"\napi_key = Zx9Qw8Er7Ty6Ui5Op4')
    assert "Hunter2-xyz!9" not in text and "Zx9Qw8Er7Ty6Ui5Op4" not in text and len(found) == 2, (text, found)

    harmless = [
        "token = get_token(request)",
        "api_key = self.settings.api_key",
        "password: ${DB_PASSWORD}",
        "secret = <your secret here>",
        "The password field must be at least eight characters.",
        "token: changeme",
        "api_key = os.environ['API_KEY']",
        "Use a personal access token with repo scope.",
        "password = example_password",
        "already [REDACTED:github-token] here",
    ]
    for line in harmless:
        assert secrets_scan.redact(line) == (line, []), (line, secrets_scan.redact(line))

    text, _ = secrets_scan.redact(f"a {GITHUB}")
    assert secrets_scan.redact(text) == (text, []), "redacting twice changes nothing"

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "sources" / "a").mkdir(parents=True)
        (root / "sources" / "a" / "clean.md").write_text("[REDACTED:github-token]\n")
        assert secrets_scan.scan(root, ["sources", "missing"]) == []
        (root / "sources" / "a" / "leak.txt").write_text(f"x\n{GITHUB}\n")
        assert secrets_scan.scan(root, ["sources"]) == ["sources/a/leak.txt:2: unredacted github-token"]
