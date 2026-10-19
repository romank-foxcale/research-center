#!/usr/bin/env python3
"""Test secret redaction: each token format is caught, values never reach the report, and code or prose
that only looks like an assignment is left alone."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Imported by its package path, the name mutation testing gives the module's functions.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ingest import secrets_scan

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


def test_credential_shapes() -> None:
    # A symbol counts as a character class: lower, digit and symbol make three.
    assert secrets_scan.redact('password = "hunter2-xyz!"')[1] == [{"kind": "assigned-secret", "line": 1}]
    # Two classes are enough from 20 characters on, unless the value is an identifier.
    assert secrets_scan.redact("api_key = abcdefghij-klmnopqrs")[1] == [{"kind": "assigned-secret", "line": 1}]
    for line in (
        "api_key = abcdefghij-klmnopqr",  # 19 characters
        "token = abcdefghijklmnopqrst_uvw",  # an identifier
        "token = some-thing-here",  # two classes, short
        "secret = config.Get(KEY_1)",  # a call, however mixed
        "db: postgres://app:pw[REDACTED:url-credentials]@db.internal/app",  # already redacted
    ):
        assert secrets_scan.redact(line) == (line, []), line


def test_adjacent_secrets_and_lines() -> None:
    _, found = secrets_scan.redact(f"{GITHUB}{KEY}{GITHUB}")
    assert found == [
        {"kind": "github-token", "line": 1},
        {"kind": "private-key", "line": 1},
        {"kind": "github-token", "line": 4},
    ], found
    assert secrets_scan.redact(f"\n{GITHUB}")[1] == [{"kind": "github-token", "line": 2}]


def test_scan_reads_broken_bytes(tmp_path: Path) -> None:
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "dump.txt").write_bytes(b"\xff\xfe\n" + GITHUB.encode())
    assert secrets_scan.scan(tmp_path, ["sources"]) == ["sources/dump.txt:2: unredacted github-token"]


def test_main(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["secrets_scan.py", str(tmp_path)])
    assert secrets_scan.main() == 2
    assert capsys.readouterr().err == "usage: secrets_scan.py <root> <folder>...\n"

    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "clean.md").write_text("nothing here\n")
    monkeypatch.setattr(sys, "argv", ["secrets_scan.py", str(tmp_path), "sources", "notes"])
    assert secrets_scan.main() == 0
    assert capsys.readouterr().out == "secret scan passed: sources, notes\n"

    (tmp_path / "sources" / "leak.md").write_text(f"{GITHUB}\n")
    monkeypatch.setattr(sys, "argv", ["secrets_scan.py", str(tmp_path), "sources"])  # one folder is enough
    assert secrets_scan.main() == 1
    assert capsys.readouterr().err == (
        "secret scan failed (redact the values, then re-run ./rc check):\n"
        "- sources/leak.md:1: unredacted github-token\n"
    )
