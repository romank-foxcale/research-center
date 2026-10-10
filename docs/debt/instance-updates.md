---
id: debt.instance-updates
title: Instances do not receive template updates
status: active
summary: An instance is a copy of the template's files, so an RC made before a template change keeps its old scripts, skills and settings; it needs the screener role, new settings, evidence types and a Living section in new briefs by hand.
verified_at: 2026-10-11
evidence:
  - scripts/materialize-template.py
  - install/rc-kit
relations:
  - docs/debt/index.md
  - plans/active/living-research.md
---

# Instances do not receive template updates

## Statement

`rc-kit new` and `./rc bootstrap install` copy every tracked template file into the instance, and `rc-kit update` updates only the kit. The living-research changes added a pipeline slot (screener), settings (`resultsPerQuery`, `screenBatch`, snowballing, `refreshCalls`, `contactEmail`), `catalog/evidence-types.json`, `catalog/adapters/` and a required `## Living` brief section. An older instance fails `./rc validate` until it gets them, and `./rc validate` names what is missing.

## Removal condition

An `rc-kit upgrade <name>` (or `./rc bootstrap upgrade`) that replaces template-owned files (scripts, skills, templates, flake), merges new settings and roles into the instance's own, and leaves data (sources, knowledge, research, catalog edits) untouched, tested on an instance made from an older commit.
