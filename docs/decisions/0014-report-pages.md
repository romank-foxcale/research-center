---
id: decision.0014-report-pages
title: Research is shared as computed, self-contained HTML pages, published as private artifacts
status: accepted
summary: rc report renders a topic's committed outputs (or a profile's dashboard with every topic's page beside it) into self-contained HTML deterministically, with no agent call; pages are derived and kept in .rc-local/reports/, redacted on the way out, with web text escaped; the rc-share skill publishes them as private claude.ai artifacts after the user confirms, and records each link so a later share updates it.
verified_at: 2026-10-18
evidence:
  - scripts/report/report.py
  - scripts/report/report_test.py
  - scripts/report/home.py
  - scripts/report/home_test.py
  - .agents/skills/rc-share/SKILL.md
  - rc.py
relations:
  - docs/decisions/0004-research-pipeline.md
  - docs/decisions/0015-profiles.md
  - docs/architecture/research-center.md
---

# Research is shared as computed, self-contained HTML pages, published as private artifacts

## Context

Research results lived only as Markdown in the repository. People who decide on them, such as a company's CTO and CEO, do not read the repository. The user asked on 2026-10-16 for results with summaries they can share, and for research they can see visually. Plan: plans/active/report-ui.md.

## Decision

- **Computed, not written.** `rc report <topic>` renders the topic's committed outputs into one page:
  - brief, source plan, screening, claims, ideas, judgement, fit, watch, deltas and report.

  It makes no model call, so it costs no budget, and the same outputs give the same bytes. A stage that has not run shows as missing and is never guessed.
- **Decisions first.** The first screen holds:
  - the report's "In plain words" summary (added 2026-10-18 after the first foxcale report proved too dense for a leader to read): about 250 words (at most 350), no claim ids, and checked by the runner like the rest of the report;
  - the bottom line with its evidence (the report's TL;DR);
  - the ideas by ring, with the judge's verdict, effort, what each replaces, risks and next step;
  - each question's certainty, with its downgrades.

  Below it come:
  - the evidence: the screening funnel, claim verdicts, source reliability and evidence types;
  - each hypothesis matrix, ranked by inconsistent surviving evidence;
  - the assumptions and the full report, with every `[C#]` linked to its claim;
  - the claims and sources, and a living topic's history.
- **A dashboard per profile.** `rc report` without a topic writes `index.html` with every topic's page beside it, linked both ways. It shows:
  - the profile's type, description and interest tags (or its scope's Who, without the scope's evidence paths);
  - each topic's status, progress, rings, leading ideas and certainty.
- **The main screen** (`rc home`, added 2026-10-18 with scouting, ADR 0016) is written to `.rc-local/reports/home/`:
  - every profile with its type, description and tags, and its open technology cards grouped by verdict;
  - a flag on any card whose licence the profile cannot use, or whose verdict the sceptic changed;
  - one page per card, with plain words before the engineers' part, the sceptic's review and the evidence quotes;
  - each profile's research dashboard and topic pages under `<profile>/research/`, linked up to the main screen.

  The folder is shared whole.
- **Derived and local.** Pages go to `<data root>/.rc-local/reports/` through `rc.write_text`, so secrets are redacted like every runner write. They are not committed, and they can be rebuilt at any time.
- **No injection, no dependencies at view time.**
  - Markdown is rendered by markdown-it-py with raw HTML off, and every other value is escaped. Links are http and https only.
  - CSS, charts and the claim filter are inline, with no CDN. Pages work offline, as files, and as artifacts.
  - Colour tokens cover light, dark and an explicit theme. Pages work at phone width without horizontal scroll.
- **Sharing is the user's act.** The `rc-share` skill:
  - builds the page with `--manifest`, which writes a content-only share copy to `share/` for an artifact to wrap in its own document;
  - confirms with the user;
  - publishes a private artifact, with a dashboard's topic pages published beside it as whole documents;
  - records the link with `--shared-at` in `.rc-local/reports/shares.json`, so the next share updates the same link.

  The link goes only to whom the user chooses.

## Consequences

- Changing what a page says means changing the brief, a source or a role and re-running, as for every research output. The HTML is never edited.
- Shared links are recorded per machine. Another person shares from their own account under their own link.
- Explainer briefs for video or slides (`rc explainer`, report-ui WP4) are deferred until a real profile topic exists to test them on.
