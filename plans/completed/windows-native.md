# windows-native: The RC runs natively on Windows with uv and Python, Claude-only by default

Lifecycle: completed
Planning status: accepted

## Outcome

The RC installs and runs on native Windows with no WSL and no Nix. The same code still runs on macOS, Linux and WSL.

- One command-line entry point, `rc.py`, replaces the bash `rc`. Thin launchers `rc.cmd` and `rc.ps1` (and `rc` for POSIX shells) run it through `uv` in the instance's locked environment.
- `pyproject.toml` and `uv.lock` pin every Python dependency. Document conversion uses pure-Python libraries, so no system binary (pandoc, poppler) is needed.
- `rc check` runs the validators and every test suite in Python. It replaces `nix flake check`.
- Every default role runs on Claude through Claude Code. GPT returns later through Pi once the workspace allows it. Cursor support is removed.
- The Windows installer and `rc-kit` work natively (`%USERPROFILE%\Projects\<name>_RC`). `rc upgrade` brings an existing instance's template-owned files up to date.

## Non-goals

- Use-case scopes and technology scouting: the next plan, which builds on this one.
- Pi as a provider: added when the ChatGPT workspace allows third-party sign-in.
- Keeping Nix as an alternative: one supported toolchain, not two.

## Evidence and current behavior

- `./rc` is a bash script, and `rc.cmd` forwards into WSL. `nix/tools.nix` supplies pandoc, pdftotext, python-pptx and openpyxl. `./rc check` runs `nix flake check`.
- A probe on native Windows on 2026-10-16 ran each CLI with the RC's read-only command line. A run passes when the agent reads a marker file and can create no file, either directly or through a shell.
  - Claude Code: pass.
  - Cursor CLI: pass.
  - Codex CLI 0.163.0: refused writes but also every read ("the read command was blocked by policy"), so it is unusable as a reader.
  - Pi 1.3.0: could not sign in with ChatGPT, because the workspace policy blocks third-party delegated access (`3p_delegated_access_policy_denied`). Only a global admin can change it in admin.openai.com/external-access.
- The user decided on 2026-10-16: Windows-only is the target; Claude and GPT suffice and Cursor is not needed; continue with Claude only until Pi is allowed.
- `scripts/runner/events.py` checks run liveness with `os.kill(pid, 0)`, which on Windows terminates the process: `./rc watch` would kill the run it follows.
- `subprocess.run(..., text=True)` without an encoding decodes agent output as cp1252 on Windows. Windows also does not resolve `codex` to `codex.cmd` for `subprocess` argv.

## Affected scope

| Repository | Worktree | Read/write | Interfaces |
| --- | --- | --- | --- |
| research-center | local clone `Desktop/Code/research-center` | write | `rc.py` and launchers, `pyproject.toml`, `uv.lock`, `scripts/`, `install/`, `templates/agents/`, docs |

## Invariants and decisions

- Agents stay read-only, enforced by CLI flags (ADR 0003). Claude's allow-list passed the Windows probe.
- `rc.py` keeps every command and option of `./rc`, so skills and docs change only in how the command is spelled: `rc` on Windows, `./rc` elsewhere.
- Extraction keeps its contract: the same stored names and the same Markdown-ish text. Licences must be permissive, so no AGPL libraries (PyMuPDF and ebooklib are excluded).
- An ADR records the toolchain decision and supersedes the Nix parts of earlier notes.

## Open questions

| Question | Impact | Owner/next evidence |
| --- | --- | --- |
| Does Claude Code on Windows run project hooks through Git Bash, so `scripts/hook` keeps working? | Rule hooks | Resolved 2026-10-16: in Claude Code on native Windows, the pre-bash hook denied a `git commit --dry-run` whose message credited an AI. |

## Work packages

| ID | Outcome | Write scope | Depends on | Completion check |
| --- | --- | --- | --- | --- |
| WP1 | `rc.py` with every command, `rc.cmd`/`rc.ps1`/`rc` launchers, `pyproject.toml` + `uv.lock`, `rc check` in Python; Nix removed; cross-platform process liveness, UTF-8 subprocess output, Windows executable resolution | repo root, `scripts/runner/`, `flake.*`, `nix/` | - | `rc check` passes on native Windows and in WSL |
| WP2 | Pure-Python extraction: PDF (pypdfium2), DOCX (mammoth), HTML (markdownify), EPUB and ODT (zip + markdownify), RTF (striprtf), PPTX and XLSX as before | `scripts/ingest/extract.py` | WP1 | Fixture documents of every type extract on Windows with no system binary |
| WP3 | Claude-only default roles, Cursor removed, provider tests with cross-platform fake CLIs | `templates/agents/`, `templates/research-center.json`, `scripts/runner/providers*.py`, validator | WP1 | `providers_test` passes on Windows; the default pipeline validates with Claude roles only |
| WP4 | Native installer and `rc-kit` for Windows, `rc upgrade` for existing instances, ADR, README, GUIDE, BOOTSTRAP and skills updated | `install/`, `scripts/`, `docs/`, skills | WP1-WP3 | A fresh instance is created with `rc-kit new` on Windows and runs `rc check`; the four-day-week instance upgrades and validates |

## Integration and verification

`rc check` on native Windows, plus one real smoke run: an `rc research refresh` of the four-day-week topic, or a short new topic, run natively.

## Failure, rollback and stop conditions

- If Claude Code on Windows cannot run the rule hooks, keep the bash `scripts/hook`, since Claude Code requires Git Bash on Windows, and record it.
- If a pure-Python extractor is clearly worse on real documents than pandoc or pdftotext, stop and decide with the user before shipping it.

## Acceptance criteria

- No WSL, Nix, pandoc or poppler is needed on Windows.
- `rc check` passes on Windows. The read-only probe still passes for every default role.
- An existing instance can be upgraded with one command.

## Lifecycle closure

- state: completed
- date: 2026-10-16
- evidence: rc check passes 12/12 natively on Windows; a fresh RC made with rc-kit new on Windows passes its own rc check and adapter fixtures; a copy of the four-day-week instance (bash rc, Nix, Cursor judge) upgraded with rc upgrade --reset-roles to Claude-only roles, no Nix files, research intact, and passes rc check; Claude Code read-only probe passed and the rule hooks fire on Windows
