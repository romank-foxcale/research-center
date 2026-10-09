---
id: decision.0005-rule-hooks
title: Claude Code hooks enforce the hard rules at tool-call time
status: accepted
summary: The CC's rule hooks are reused - AI attribution in commits and PRs is denied, Nix bypasses ask, stray Markdown is denied, notes are validated on edit and skill drift is reported on stop - with knowledge/, research/ and sources/ added as Markdown folders.
verified_at: 2026-10-09
evidence:
  - scripts/rule_hooks.py
  - scripts/rule_hooks_test.py
  - scripts/agent-configs.py
relations:
  - docs/index.md
---

# Claude Code hooks enforce the hard rules at tool-call time

## Decision

`scripts/rule_hooks.py` is a copy of the CC's hooks. `./rc agents sync` writes its hooks block into `.claude/settings.json`. The RC adds `knowledge/`, `research/` and `sources/` to the folders where Markdown may live, and `research-center.json` may declare more in `markdownDirs`.

## Limits

The hooks only run in Claude Code. `./rc check` stays the source of truth.
