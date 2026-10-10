---
id: decision.0008-search-and-screen
title: Research searches the planned adapters, screens every result with a logged reason, and tests its hypotheses
status: accepted
summary: The planner writes adapter queries, hypotheses with a disconfirming avenue each, a horizon and numbered exclusion criteria; the runner runs every query (search), a screener includes or excludes each result against those criteria with a reason (screen), included records are stored for the researchers, and the report shows the PRISMA-style flow.
verified_at: 2026-10-11
evidence:
  - scripts/research/research.py
  - scripts/research/research_test.py
  - .agents/skills/research-plan-sources/SKILL.md
  - .agents/skills/research-screen/SKILL.md
relations:
  - docs/decisions/0004-research-pipeline.md
  - docs/decisions/0007-source-adapters.md
  - docs/architecture/research-center.md
---

# Research searches the planned adapters, screens every result with a logged reason, and tests its hypotheses

## Context

With source adapters (ADR 0007) the RC can search far more than the web, but searching is only half of a defensible review. A reader must be able to see what was found, what was dropped and why (PRISMA 2020). A plan that only looks for support confirms what it expected (horizon scanning, Analysis of Competing Hypotheses). Plan: plans/active/living-research.md, WP2.

## Decision

- **plan** returns `horizon` (near, medium, long), `hypotheses` H1.., `exclusions` X1.. each naming the brief section it comes from, and `avenues`, each one query on one adapter or `web`, with filters, since, stance (support, disconfirm, explore) and the questions it serves. The runner rejects a plan that:
  - lacks a disconfirming avenue for some hypothesis;
  - leaves a question without an avenue;
  - uses an unknown adapter or filter;
  - uses fewer than two adapter families besides the web.

  The runner adds X0 (bears on no question).
- **search** (no agent): the runner runs every adapter avenue and logs each query in `searches.json`. Results merge by key into `candidates.json` (R1..), keeping which avenues and questions found them. A failing adapter is logged and skipped. If every adapter avenue fails, the run stops rather than silently becoming web-only.
- **screen**:
  - The runner excludes records flagged as retracted.
  - The screener role (claude sonnet, read-only, batches of `research.screenBatch`) decides on every other record. An exclusion names one criterion, an inclusion the questions it bears on, and both give a reason.
  - Included records are stored under `sources/search-<topic>/`. Scholarly records and books are stored as metadata and abstract; other records as the fetched page, falling back to metadata.
  - The outputs are `screening.json` and `screening.md`, with the flow: identified, duplicates, screened, excluded by criterion, included.
- **collect**: the researchers read the included records first, then search the web along the `web` avenues. A cited URL that matches an included record (by DOI or canonical URL) reuses its stored text, so its quotes are checked against what was screened. Included records do not count against `maxSourcesPerResearcher`.
- **report**: the runner appends "How the sources were found": the flow and the number of web pages the researchers added.

## Consequences

- The pipeline has nine stages. A default run costs about 10 agent calls plus one per extra screening batch and retries; `budget.researchCalls` defaults to 32.
- Every exclusion is visible and arguable. A user who disagrees edits the brief or the criteria and re-runs from plan.
- Instances made before this decision need `catalog/agents/screener.json`, `pipeline.screener`, `research.resultsPerQuery` and `research.screenBatch`. `./rc validate` names what is missing.
