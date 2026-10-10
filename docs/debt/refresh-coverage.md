---
id: debt.refresh-coverage
title: A refresh searches less than a full run
status: active
summary: A refresh re-runs only the saved adapter queries since the last check: it does not search the web, does not snowball, and OpenAlex filters by publication date, so works published earlier but indexed late are missed.
verified_at: 2026-10-11
evidence:
  - scripts/research/living.py
  - scripts/sources/adapters/openalex.py
relations:
  - docs/debt/index.md
  - plans/active/living-research.md
---

# A refresh searches less than a full run

## Statement

This keeps a refresh with nothing new free of agent calls. The gaps are closed by the next full run (`./rc research run <topic>` after an amendment, or `--from search`).

## Removal condition

A refresh that also snowballs from newly included records, and an OpenAlex query on creation date where the API offers it to all users, measured on a living topic for cost against what they add.
