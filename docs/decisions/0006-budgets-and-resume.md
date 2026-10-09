---
id: decision.0006-budgets-and-resume
title: Every run has an agent call budget and resumes from what it already committed
status: accepted
summary: Ingest and research count agent calls against budget.ingestCalls and budget.researchCalls; reaching the budget stops the run with finished work kept, and the next run skips unchanged sources (manifest fingerprint) and finished stages (their outputs).
verified_at: 2026-10-09
evidence:
  - scripts/runner/rc.py
  - scripts/ingest/ingest.py
  - scripts/research/research.py
relations:
  - docs/decisions/0004-research-pipeline.md
---

# Every run has an agent call budget and resumes from what it already committed

## Context

Large corpora and multi-model critique can exhaust subscription rate limits. The user asked for a limit, and a run that hits it must never silently truncate.

## Decision

- `Session.reserve` counts every agent call, retries included, and stops with BudgetExceeded once the budget is spent. `--budget N` overrides it for one run.
- Ingest writes each source's text and digest as soon as they are done. A digest records its manifest fingerprint, and a source whose fingerprint did not change is skipped. Notion and Drive sources are re-read on every run, because only a fetch shows whether they changed.
- Research resumes at the first stage without its output. `--from <stage>` clears that stage and every later one.

## Defaults

60 ingest calls and 24 research calls, in templates/research-center.json.
