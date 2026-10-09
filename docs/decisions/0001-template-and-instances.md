---
id: decision.0001-template-and-instances
title: The RC is a public template; instances are private; the RC never touches product code
status: accepted
summary: research-center ships no data and is copied into private instances by ./rc bootstrap install; ideas worth acting on leave as a Control Center task plan, so code changes always go through a CC's worktrees and gates.
verified_at: 2026-10-09
evidence:
  - install/rc-kit
  - BOOTSTRAP.md
  - scripts/materialize-template.py
  - scripts/validate-research-center.py
  - scripts/research/research.py
relations:
  - docs/architecture/research-center.md
  - docs/decisions/0002-committed-extracted-sources.md
---

# The RC is a public template; instances are private; the RC never touches product code

## Context

The RC is for companies (repos, Notion, Drive) and for individuals (articles, books, papers). Both need the same machinery, and neither wants its material in a shared repo. The user's Control Center already owns code changes, with worktrees, councils and verify gates.

## Decision

- The template holds no data. `validate-research-center.py` fails a template that contains sources, knowledge, research or source catalog entries.
- `rc-kit new <name>` (or `./rc bootstrap install <dir>` from a template clone) makes an instance, exactly as `cc-kit new` makes a Control Center: the tracked files minus the template's own plans, research-center.json from templates/, default roles in catalog/agents, empty data folders, and `git init`.
- The RC never writes product code, and never writes into a CC. The apply stage writes `research/<topic>/handoff.md` in the CC task-plan format (templates/task-plan.md is the CC's), and the user carries it over.

## Consequences

- Improving the template does not reach existing instances automatically. An instance pulls template changes as an ordinary Git merge, if the user wants them.
- "Testing an idea against our needs" is an assessment in the RC. A real trial is a CC feature.
