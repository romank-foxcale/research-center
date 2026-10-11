---
id: debt.checks-of-form
title: Grades and language are checked for form, not truth
status: active
summary: The runner checks that every grade, certainty, matrix and likelihood word has the required shape, arithmetic and reason, and that hedges from a fixed list are absent; whether a grade or rating is right rests on the roles and on the user.
verified_at: 2026-10-11
evidence:
  - scripts/research/research.py
  - docs/decisions/0010-evidence-grading.md
  - docs/decisions/0011-structured-analysis.md
relations:
  - docs/debt/index.md
  - docs/decisions/0011-structured-analysis.md
---

# Grades and language are checked for form, not truth

## Statement

Reliability is capped by evidence type, certainty must add up from named downgrades, matrices may only weigh searched hypotheses, and the sceptics and judge review independently. Still, a model can grade generously within those bounds, and vague phrasing outside the hedge list passes the language check.

## Removal condition

Calibration data from real topics: compare grades and certainties with how the evidence later moved (verdict history across refreshes), and tighten the rubrics or add an independent grading role where they drift.
