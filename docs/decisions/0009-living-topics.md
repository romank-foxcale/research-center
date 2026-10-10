---
id: decision.0009-living-topics
title: A topic with a cadence stays living - refreshed incrementally, versioned, with stable claim ids, verdict history and a delta per refresh
status: accepted
summary: A brief's Living section sets a cadence and a retire-when; after the first full run the adapter searches are saved in watch.json; ./rc research refresh re-runs them since the last check, screens only unseen records (screening.json is the seen set), collects claims from new included records with the next ids, re-derives the conclusions only when new verified evidence arrived, keeps verdict and ring history per version, and writes delta/<date>.md with what needs the user's review.
verified_at: 2026-10-11
evidence:
  - scripts/research/living.py
  - scripts/research/research.py
  - scripts/research/research_test.py
relations:
  - docs/decisions/0008-search-and-screen.md
  - docs/decisions/0006-budgets-and-resume.md
  - docs/architecture/research-center.md
---

# A topic with a cadence stays living - refreshed incrementally, versioned, with stable claim ids, verdict history and a delta per refresh

## Context

A one-shot report starts going stale on the day it is written. Living systematic reviews re-search on a fixed cadence, screen only what is new, and change their conclusion only when the evidence does, with every published state versioned. Plan: plans/active/living-research.md, WP4.

## Decision

- **The brief decides.**
  - `## Living` holds `Cadence:` (none, weekly, monthly, quarterly, or derived) and `Retire when:`. derived means 30 days for a near horizon and 91 for medium or long, clamped to weekly-quarterly; the grading work will refine it with evidence half-lives.
  - `## Amendments` logs changes after acceptance.
  - Status runs draft → accepted → living ↔ paused, and retired is final.
- **watch.json** is written after a complete run of a topic with a cadence. It holds the cadence, the brief hash, the version, the check dates, and the plan's adapter avenues whose adapter is watchable. Web avenues stay with the researchers and are not saved.
- **refresh** (living.py):
  1. Re-run the saved queries since `lastChecked`.
  2. Keep the records whose key is not in screening.json, which is the seen set (no separate seen.json). A watched page whose fingerprint changed counts as new.
  3. Check retractions, then screen the new records with the plan's criteria. Included ones are stored by appending to the source and added to screening.json.
  4. The researchers read only the new included records, without web search. Their claims get the next ids, and existing claims never change.
  5. If any new claim's quote verified, the version goes up and analyze, critique, judge, apply and report run again on the whole ledger. The analyst keeps the ids of ideas that are still the same idea.
  6. Write `delta/<date>.md` and `.json`: new records with their decisions, new claims, and a **Needs your review** section listing flipped claim and idea verdicts, moved fit rings and newly contested claims. The report's header gets the version and the check and change dates.
- **Material change is new verified evidence**, not a predicted verdict change. Predicting whether a verdict would move needs the same critique and judgement that re-deriving does. So the RC re-derives whenever verified evidence arrives, and the delta says whether the conclusions actually moved ("new evidence, conclusions unchanged" is a valid outcome). With no new verified evidence there is no new version and no agent call beyond screening and collecting.
- **History**: judgement.json keeps a `history` of `{version, date, verdict}` per claim and idea, and fit.json one of `{version, date, ring}` per idea. Items not re-judged are carried with their history. A full re-run (`run`, or `--from`) renumbers claims and starts the history again at the next version.
- **Resumable**: a refresh records its step in watch.json `pending` (screened, collected, rederiving) and its snapshot of the conclusions before it began. An interrupted refresh resumes from that step, and accepted agent replies are reused as in a run (ADR 0006).
- **An amended brief is never refreshed.** Its saved searches no longer match what is asked. `run` notices the changed brief hash in source-plan.json and redoes everything from plan as the next version.
- **Scheduling stays outside the RC.** `./rc research refresh --due` refreshes every living topic whose cadence has elapsed and skips paused and retired ones. cron or Task Scheduler runs it (GUIDE.md). `budget.refreshCalls` (default 16) caps each refresh.

## Consequences

- A refresh with nothing new is free. One with new verified evidence costs about as much as the second half of a run (around 9 calls).
- A refresh does not snowball and does not search the web. A full re-run does both.
- OpenAlex filters by publication date, so a work published earlier but indexed only now is missed by `since`. It is found by the next full run.
