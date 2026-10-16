---
id: debt.cursor-no-web
title: Cursor roles cannot search the web or read connectors
status: superseded
summary: Cursor (Grok) is confined to a read-only snapshot with a deny config, which has no proven web-only permission, so Grok judges and critiques but never researches.
verified_at: 2026-10-16
evidence:
  - scripts/runner/providers.py
relations:
  - docs/decisions/0012-windows-native-uv.md
  - docs/decisions/0003-read-only-agents.md
  - docs/debt/index.md
---

> Superseded on 2026-10-16: Cursor support was removed; every default role runs on Claude. See [docs/decisions/0012-windows-native-uv.md](../../docs/decisions/0012-windows-native-uv.md).

# Cursor roles cannot search the web or read connectors

## Statement

cursor-agent's permission config could block Write and Shell, as proven in the CC. No probe has shown a configuration that allows web search while still blocking writes. So the provider refuses web-read and connector-read for cursor.

## Removal condition

Run a probe like `providers.py probe` that shows cursor-agent searching the web while refusing Write and Shell. Then add web-read for cursor.
