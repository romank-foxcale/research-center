---
id: decision.0010-evidence-grading
title: Evidence is graded on separate axes - source reliability capped by evidence type, claim credibility, answer certainty - and re-checked when it goes stale
status: accepted
summary: catalog/evidence-types.json gives each domain-agnostic evidence type a reliability ceiling and a half-life; researchers grade each source A-F with a reason (capped by its type) and mark second-hand claims with via; the judge grades each claim's credibility 1-6 and each answer's certainty GRADE-style from named downgrades the runner adds up; a refresh re-fetches pages past their half-life and marks claims whose quote is gone as drifted.
verified_at: 2026-10-11
evidence:
  - templates/evidence-types.json
  - scripts/research/research.py
  - scripts/research/living.py
  - scripts/research/research_test.py
relations:
  - docs/decisions/0004-research-pipeline.md
  - docs/decisions/0009-living-topics.md
  - docs/architecture/research-center.md
---

# Evidence is graded on separate axes - source reliability capped by evidence type, claim credibility, answer certainty - and re-checked when it goes stale

## Context

A verified quote proves a page says something, not that it is true, nor how far an answer resting on it can be trusted. Intelligence analysis grades the source and the information separately (the NATO / Admiralty system). Evidence-based medicine grades the certainty of a conclusion by naming what lowers it (GRADE). Both work for any subject once the evidence types are not medical. Plan: plans/active/living-research.md, WP5.

## Decision

- **Evidence types are data.** `catalog/evidence-types.json` (seeded from `templates/evidence-types.json`) lists the adapters' vocabulary of 19 types, from dataset and systematic review to forum and unknown. Each type has a `reliabilityCeiling` (the best grade it can earn) and a `halfLifeDays` (when its claims are due for a re-check). An instance tunes the numbers; the validator keeps the ids equal to the adapters' list.
- **Source reliability, A to F.** Researchers give every source an `evidenceType`, a `reliability` grade and a `reliabilityReason`. The runner caps the grade at the type's ceiling and records when it did. An included record keeps the type its adapter gave it. The old free `kind` field is gone.
- **Second-hand claims are marked.** A claim whose page only reports another source names that original in `via`. The runner marks it `traced` when the original's URL is itself in the ledger (SIFT: trace claims to the original). Sceptics treat untraced second-hand claims as at best WEAK.
- **Claim credibility, 1 to 6**, is given by the judge with every verdict. It is separate from the source's reliability: a reliable source can be wrong on one point.
- **Answer certainty, GRADE-style.** The judge grades every question's answer:
  - It starts at high and is lowered for named `downgrades`: reliability, inconsistency, indirectness (evidence about a different setting than the brief's needs), imprecision, and one-sided (only interested parties measured it). Each downgrade is 1 or 2 levels, with a reason and the claims it concerns.
  - It can be raised for `upgrades`: large-effect or convergence.
  - The runner rejects a certainty that is not what the levels add up to. The validator rejects an answer without certainty or a grade without a reason.
  - The report appends each answer's certainty with its reasons, and the evidence table shows reliability and credibility.
- **Staleness.** A refresh re-fetches every stored page whose type's half-life has passed since `checkedAt`. Scholarly records stored as abstracts are not re-fetched; retraction checks cover them. If the page no longer holds a verified quote, or cannot be fetched, the claim is marked `drifted` and stops counting as verified. The page is stored as it reads now. A drifted claim the conclusions rest on makes the refresh material, so it is re-critiqued and re-judged, and the delta lists it under Needs your review.

## Consequences

- Reports say how sure each answer is and why. Two reports on different subjects are comparable on the same scales.
- Grades come from models and are checked only for shape and arithmetic, not for truth. The ceiling limits how wrong a reliability grade can be, and the reasons make each grade arguable.
- Topics researched before this decision have ungraded ledgers. They render with "?" and get graded on their next full run.
