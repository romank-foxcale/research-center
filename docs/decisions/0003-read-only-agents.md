---
id: decision.0003-read-only-agents
title: Agent roles only read; access levels are enforced by CLI flags; provider code is copied from the CC
status: accepted
summary: Every RC role runs headless under the user's subscription with read-only, web-read or connector-read access enforced by its CLI's flags or config; the runner writes all files; providers.py is a deliberate copy of command_center_template@6489510.
verified_at: 2026-10-16
evidence:
  - scripts/runner/providers.py
  - scripts/runner/providers_test.py
  - scripts/runner/rc.py
relations:
  - docs/architecture/research-center.md
  - docs/decisions/0012-windows-native-uv.md
---

# Agent roles only read; access levels are enforced by CLI flags; provider code is copied from the CC

## Context

The RC runs on the user's own subscriptions: Claude by default, Codex (ChatGPT) optionally. Cursor was supported until 2026-10-16 (docs/decisions/0012-windows-native-uv.md). Unlike CC writers, no RC role needs to write: replies are data that the runner checks and stores.

## Decision

| Access | Claude | Codex |
| --- | --- | --- |
| read-only | `--tools` and `--allowedTools` Read, Grep, Glob; `--strict-mcp-config`; `dontAsk` | `--sandbox read-only` |
| web-read | adds WebSearch and WebFetch | `codex --search exec` (native web search) |
| connector-read | `dontAsk` with an allow-list: Read, Grep, Glob, ToolSearch and the connectors' search, fetch and read tools. No `--tools` and no strict MCP config, because claude.ai connectors load late and surface through ToolSearch | refused |

On 2026-10-09, probes with claude 2.1.295 and codex-cli 0.160.1 showed:

- connector tool names `mcp__claude_ai_Notion__*` and `mcp__claude_ai_Google_Drive__*`;
- `dontAsk` refusing an unlisted Notion tool and Write;
- `codex --search exec` running web searches.

On 2026-10-16 the same read-only command line was probed on native Windows. Claude Code read a marker file and could create no file, directly or through a shell. Codex 0.163.0 could not create a file either, but its sandbox also blocked every command it reads files with, so Codex roles are for macOS, Linux and WSL until that changes.

`providers.py` was copied from command_center_template@6489510. The RC changed its access levels and dropped write-worktree. Later CC fixes, such as provider CLI flag changes, are ported as deliberate diffs.

## Consequences

- A provider that is logged out fails the call. There is no fallback model.
- When a CLI renames a flag or a connector tool, the provider tests and the next run fail, rather than access silently widening.
