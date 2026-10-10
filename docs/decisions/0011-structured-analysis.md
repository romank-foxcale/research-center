---
id: decision.0011-structured-analysis
title: Analyses weigh competing hypotheses in a matrix and name their assumptions; reports say likelihood on a fixed scale and mark evidence from assessment
status: accepted
summary: For a question the plan gave two or more hypotheses, the analyst rates every relied-on claim C, I or N against each, and the runner ranks the hypotheses by surviving inconsistent evidence and names the diagnostic claims; every answer lists its key assumptions, which sceptics and the judge rule on; the report may only use ICD 203 likelihood words its certainty allows, and every paragraph of its answers cites a claim or is marked Assessment.
verified_at: 2026-10-11
evidence:
  - scripts/research/research.py
  - scripts/research/research_test.py
  - .agents/skills/research-analyze/SKILL.md
  - .agents/skills/research-report/SKILL.md
relations:
  - docs/decisions/0008-search-and-screen.md
  - docs/decisions/0010-evidence-grading.md
  - docs/architecture/research-center.md
---

# Analyses weigh competing hypotheses in a matrix and name their assumptions; reports say likelihood on a fixed scale and mark evidence from assessment

## Context

A model that writes an answer tends to collect support for the first plausible hypothesis, to rest it on unstated assumptions, and to hedge in words that mean nothing measurable ("probably", "may well"). Structured analytic techniques address exactly these failures:

- Heuer's Analysis of Competing Hypotheses and the key assumptions check.
- The analytic standards of ICD 203: calibrated likelihood words, and keeping what the evidence shows apart from what the analyst judges.

Plan: plans/active/living-research.md, WP6.

## Decision

- **Competing hypotheses.** The analysis's JSON gains `questions`: one entry per brief question.
  - For a question with two or more plan hypotheses, an `ach` matrix is required. It covers all of them and rates every claim the answer relies on as `C`, `I` or `N` against each.
  - Only hypotheses of the plan may be weighed, and each must have a disconfirming search in the plan. Otherwise the analysis is rejected. An alternative nobody searched against goes under `untested` and is reported as a gap.
  - Matrix claims count as relied on, so they are critiqued.
  - The runner ranks the hypotheses by how many claims inconsistent with them survived the judgement (REFUTED and UNSUPPORTED claims don't count), fewest first. It also lists the diagnostic claims, the ones rated differently across the hypotheses. Ranking and diagnostics are computed, not asked of a model.
- **Key assumptions.** Every question lists at least one assumption (A1..) its answer rests on. Each sceptic gives every assumption a verdict, and so does the judge. The report appends them with the judge's verdicts.
- **Calibrated language.** In the report's TL;DR and answer sections, the runner rejects:
  - hedges that map to no number: probably, possibly, perhaps, presumably, conceivably, definitely, certainly, undoubtedly, probable, improbable, doubtful, in all likelihood;
  - scale words stronger than the question's certainty allows. Likely, unlikely and roughly even chance need at least low certainty; very likely and very unlikely need moderate; almost certain and almost no chance need high.
- **Evidence or assessment.** Every paragraph and bullet of the TL;DR and the answers cites a claim or starts with `Assessment:` (or `Certainty:`), so a reader can tell the evidence from the writer's judgement.
- Question coverage in the analysis and the report now matches question ids as whole words, so Q10 no longer counts as answering Q1.

## Consequences

- Reports rank competing answers on the evidence that tells them apart, and show what an answer assumes and how that assumption fared.
- The language rule is lexical. It catches the listed words, not every vague phrasing, and it checks scale words in the TL;DR only for hedges, since a TL;DR bullet may span questions.
- An analysis without assumptions, or without a matrix where one is due, costs a retry.
