---
id: decision.0012-windows-native-uv
title: The RC runs natively on Windows through uv and Python, with Claude-only default roles
status: accepted
summary: rc.py with rc.cmd, rc.ps1 and ./rc launchers replaces the bash rc and Nix; pyproject.toml and uv.lock pin the only dependencies, which are pure-Python document converters; rc check runs every validator and test suite in Python; every default role runs on Claude Code; Cursor support is removed and Codex stays optional because its Windows sandbox blocks reading.
verified_at: 2026-10-16
evidence:
  - rc.py
  - pyproject.toml
  - scripts/ingest/extract.py
  - scripts/runner/providers.py
  - scripts/runner/events.py
relations:
  - docs/decisions/0003-read-only-agents.md
  - docs/decisions/0002-committed-extracted-sources.md
  - docs/architecture/research-center.md
---

# The RC runs natively on Windows through uv and Python, with Claude-only default roles

## Context

The RC ran through a bash `./rc` inside WSL, with Nix supplying pandoc, poppler and the Python libraries and running the checks. The people who use it work on Windows: foxcale's DI `ai` repo already runs on Windows Python. A WSL distribution and a Nix install were the heaviest part of setting up an RC, for one bash script and two converters.

A probe on native Windows on 2026-10-16 ran each agent CLI with the RC's read-only command line. A run passed when the agent read a marker file and created no file, either directly or through a shell.

| CLI | Version | Result |
| --- | --- | --- |
| Claude Code | | passed |
| Cursor CLI | | passed |
| Codex CLI | 0.163.0 | refused writes, but also every read, because its Windows sandbox blocks the commands it reads with |
| Pi | 1.3.0 | was meant to carry GPT roles with read-only tools, but could not sign in: the ChatGPT Enterprise workspace denies third-party delegated access (`3p_delegated_access_policy_denied`), and Pi is not in the admin catalogue |

The user decided to target Windows, to drop Cursor, and to continue with Claude only until GPT can run read-only.

## Decision

- **One Python entry point.** `rc.py` keeps every command of the old `./rc`. `rc.cmd` and `rc.ps1` on Windows, and `./rc` on POSIX shells including Git Bash, run it with `uv run --frozen` in the environment that `pyproject.toml` and `uv.lock` pin. uv creates that environment on first use.
- **No system binaries.** Documents are converted by libraries locked in `uv.lock`:
  - pypdfium2 for PDF, one `## Page N` per page; a PDF with no text layer is skipped, since it needs OCR;
  - mammoth for DOCX;
  - markdownify for HTML, with scripts and styles dropped;
  - EPUB chapters in spine order, and ODT parsed from its XML, both refusing entity declarations;
  - striprtf for RTF;
  - python-pptx and openpyxl as before.

  Every licence is permissive, so AGPL libraries such as PyMuPDF and ebooklib are not used.
- **`rc check` replaces `nix flake check`.** It runs the validators and every test suite with the locked interpreter, reports each result, and fails if any fails.
- **Windows correctness:**
  - executables are resolved the way a shell would (`codex` to `codex.cmd`);
  - agent and git output is read as UTF-8 whatever the console code page;
  - `rc watch` checks run liveness through the Win32 API, because `os.kill(pid, 0)` terminates the process on Windows.
- **Claude-only defaults.**
  - Researchers and sceptics stay independent pairs on two models, Opus and Sonnet, and the judge runs on Opus.
  - Cursor support is removed.
  - Codex stays as an optional provider for macOS, Linux and WSL.
  - GPT returns through Pi once the workspace allows it, and that is a change of roles, not of design.

## Consequences

- Setting up an RC means installing uv, git, gh and Claude Code. There is no WSL and no Nix.
- The checks are no longer hermetic: they run in the locked environment rather than a sandbox. `uv.lock` pins the versions.
- Model diversity among the sceptics is now two Claude models rather than three vendors. The anonymous judging and the per-claim critique are unchanged.
- Instances made before this decision still have the bash `rc` and the Nix files. `rc upgrade` brings their template-owned files up to date.
