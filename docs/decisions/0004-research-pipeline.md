---
id: decision.0004-research-pipeline
title: Research is a fixed seven-stage pipeline with a claims ledger every later stage must cite
status: accepted
summary: plan, collect, analyze, critique, judge, apply and report each commit an output under research/<topic>; claims carry a stored page and a checked quote, sceptics review independently, the judge sees anonymous labels, and the report may only cite claims judged HOLDS or WEAK.
verified_at: 2026-10-10
evidence:
  - scripts/research/research.py
  - scripts/research/research_test.py
  - .agents/skills/research-sceptic/SKILL.md
  - .agents/skills/research-judge/SKILL.md
relations:
  - docs/architecture/research-center.md
  - docs/decisions/0006-budgets-and-resume.md
  - docs/decisions/0008-search-and-screen.md
---

# Research is a fixed seven-stage pipeline with a claims ledger every later stage must cite

## Context

The user wants a system that decides where to look, how to store and analyze what it finds, critiques it, and tests it against their needs, in the spirit of a newsletter that explains new AI ideas. One model that searches, writes and grades its own work goes unchallenged.

## Decision

- **plan**: one role turns the brief into search avenues, each with a reason and the questions it serves.
- **collect**: the researchers (Claude and GPT by default) work in parallel and independently. The runner merges sources by URL and downloads every cited page into `sources/web-<topic>/`. A claim's quote of at least six words is verified when it is found in the stored text as whole words, or when 80% of its five-word runs are found and every run holding a number or a negation is among them. Sources past `maxSourcesPerResearcher` are dropped together with the claims citing them.
- **analyze**: answers per question and an ideas list. Cited claim ids must exist.
- **critique**: sceptics (Claude, GPT, Grok) judge every cited claim as HOLDS, WEAK, REFUTED or UNSUPPORTED, with the burden of proof on the claim. Committed reviews are named review-a, review-b, ... in shuffled order. Which role wrote which stays in `.rc-local`.
- **judge**: sees only Review A, B, C, and settles claims and ideas (SURVIVES, WEAKENED, FALLS). A claim refuted by any reviewer but kept by the judge is recorded as contested and shown in the report.
- **apply**: ranks each surviving idea ADOPT, TRIAL, ASSESS or HOLD against the profile and the ingested sources. ADOPT and TRIAL produce the CC handoff.
- **report**: may cite only claims judged HOLDS or WEAK, and must answer every question. The runner appends the evidence table, the refuted and contested claims, and the handoff note.
- Every reply is checked against its stage's contract. A failing reply gets one retry with the problems listed. A second failure stops the run.

## Consequences

- A run of the default pipeline costs about 9 agent calls, plus retries. Search and screen (docs/decisions/0008-search-and-screen.md) add the screening batches.
- Web pages can change or disappear. The stored copy is what the claims were checked against.
