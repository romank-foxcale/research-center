---
id: decision.0003-read-only-agents
title: Agent roles only read; access levels are enforced by CLI flags; provider code is copied from the CC
status: accepted
summary: Every RC role runs headless under the user's subscription with read-only, web-read or connector-read access enforced by its CLI's flags or config; the runner writes all files; providers.py is a deliberate copy of command_center_template@6489510.
verified_at: 2026-10-09
evidence:
  - scripts/runner/providers.py
  - scripts/runner/providers_test.py
  - scripts/runner/rc.py
relations:
  - docs/architecture/research-center.md
  - docs/debt/cursor-no-web.md
---

# Agent roles only read; access levels are enforced by CLI flags; provider code is copied from the CC

## Context

The RC uses the same subscriptions as the user's Control Center: Claude, ChatGPT (Codex) and Cursor (Grok). Unlike CC writers, no RC role needs to write: replies are data that the runner checks and stores.

## Decision

| Access | Claude | Codex | Cursor |
| --- | --- | --- | --- |
| read-only | `--tools` and `--allowedTools` Read, Grep, Glob; `--strict-mcp-config`; `dontAsk` | `--sandbox read-only` | snapshot copy with a deny config, fingerprinted |
| web-read | adds WebSearch and WebFetch | `codex --search exec` (native web search) | refused |
| connector-read | `dontAsk` with an allow-list: Read, Grep, Glob, ToolSearch and the connectors' search, fetch and read tools. No `--tools` and no strict MCP config, because claude.ai connectors load late and surface through ToolSearch | refused | refused |

On 2026-10-09, probes with claude 2.1.295 and codex-cli 0.160.1 showed:

- connector tool names `mcp__claude_ai_Notion__*` and `mcp__claude_ai_Google_Drive__*`;
- `dontAsk` refusing an unlisted Notion tool and Write;
- `codex --search exec` running web searches.

`providers.py` was copied from command_center_template@6489510. The RC changed its access levels and dropped write-worktree. Later CC fixes, such as provider CLI flag changes, are ported as deliberate diffs.

## Consequences

- A provider that is logged out fails the call. There is no fallback model.
- When a CLI renames a flag or a connector tool, the provider tests and the next run fail, rather than access silently widening.
