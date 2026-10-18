---
id: decision.0016-scouting
title: Scouting turns a profile's interest tags into candidates, then technology cards, starting with discovery that uses no agent
status: accepted
summary: rc scout runs discovery, triage, technology cards and their challenge. Discovery asks, per interest tag, GitHub for new and for established active repositories, arXiv for its newest papers and OpenAlex for recent works since the last discovery; results merge by key across tags; repositories carry the profile's licence verdict; a seen-list makes each find a candidate once; a failing source is reported and never stops the rest; the user's gh token is lent to GitHub search for the run only. Triage (one call) picks the few finds worth a card; the runner stores each pick's README or paper page and sets its licence line; the evaluator writes a card for leaders and engineers with a verdict (worth testing, watch, not a fit), quoting the evidence word for word; a sceptic reviews every card and its verdict replaces a wrong one, visibly; about 12 calls a run.
verified_at: 2026-10-18
evidence:
  - scripts/scout/scout.py
  - scripts/scout/scout_test.py
  - scripts/sources/adapters/github.py
  - templates/packs/software/adapters/github.json
  - templates/research-center.json
  - scripts/scout/cards.py
  - scripts/scout/cards_test.py
  - .agents/skills/scout-card/SKILL.md
relations:
  - docs/decisions/0015-profiles.md
  - docs/decisions/0007-source-adapters.md
  - docs/architecture/research-center.md
---

# Scouting turns a profile's interest tags into candidates, then technology cards, starting with discovery that uses no agent

## Context

The user wants the job foxcale pays consultants for: hear about new technology that fits a profile, and be told plainly when it does not. A question-driven study takes 36 minutes and 20 agent calls (ADR 0004), which is too heavy to run weekly over many tags. Scouting therefore starts with a pass that costs no agent call. Plan: plans/active/scouting.md.

## Decision

- **Discovery is adapter code only.** For every interest tag, `rc scout discover` runs four searches; `scout.sources` in the settings picks them:
  - `github-new`: repositories created since the last discovery, most starred first;
  - `github-active`: repositories with at least `scout.githubMinStars` stars pushed since then;
  - `arxiv`: the newest arXiv papers with the tag in the title or abstract, through the feed adapter;
  - `openalex`: works published since then, with the tag searched as a quoted phrase, because loose word matching floods it with unrelated fields.

  A source whose adapter is not enabled is skipped and named. The GitHub sources need the software pack.
- **Since:** the last discovery date, from `scout/state.json`, or `scout.lookbackDays` (30) ago on the first run.
- **Merge.** Results merge by record key across tags and sources, so a find surfaced by several tags is one candidate carrying all of them. Candidates found by more tags come first, then by stars.
- **Licence on the candidate.** Each repository carries the profile's licence verdict (ADR 0015) from the licence GitHub reports. No licence counts as `unknown`, and unknown is flagged for a company profile.
- **Seen once.** `scout/seen.json` keeps every find that became a candidate, so the next run skips it. WP4 adds the card and dismissed statuses.
- **Failures are loud.** A source that fails, such as on rate limit or network, is listed in the run summary and the candidates file, and the other sources go on.
- **GitHub token.** When `GITHUB_TOKEN` is unset, the runner reads the user's `gh auth token` into its own process for the run, which raises GitHub search from 10 to 30 requests a minute. The token is sent only to api.github.com and never written. An adapter may name an `optionalKeyEnv`, used when set and never required.
- **Outputs, per profile and committed:**
  - `scout/candidates/<stamp>.json`;
  - `scout/runs/<stamp>-searches.json`, every query and its status;
  - `scout/seen.json` and `scout/state.json`.

- **Triage, cards and challenge** (`scripts/scout/cards.py`). `rc scout` runs discovery and then these steps, within `scout.calls` agent calls (12 by default):
  - **Triage.** The scout-triage role sees every open candidate in one call: title, kind, tags, stars, licence class and summary. It picks at most `scout.cardsPerRun` (6), each with a reason and the component it bears on. The rest are marked `passed` in the seen-list.
  - **Evidence.** For each pick the runner fetches what a card may rely on: a repository's README through the GitHub API, or a paper's arXiv page. It stores it in `scout/evidence/` with secrets redacted, together with the facts it holds, including the licence verdict. No agent sets the licence.
  - **Card.** The scout-evaluator writes one card per pick, in parallel.
    - For leaders: what it is, what it could do for the profile, where it plugs in, and the verdict (`worth testing`, `watch` or `not a fit`) with its reason.
    - For engineers: how it works, the component and what it does today, what it replaces, alternatives, pros, cons, risks, maturity, and an evaluation plan (experiment, metric, pass bar, effort).

    At least two claims quote the evidence word for word, checked like research quotes, and the fit names the profile files it rests on. "Not a fit" is a full result.
  - **Challenge.** The scout-sceptic reviews every card in one call: holds, overstated (with issues) or wrong (with the verdict that does follow). A wrong card takes the sceptic's verdict, and the card says the sceptic changed it.
  - **Storage.** Cards are `scout/cards/<id>.json`, rendered to `.md` by the runner. `rc scout dismiss` closes one, and its find is never raised again.

## Consequences

- A discovery of 17 tags makes about 68 searches and takes minutes, mostly GitHub's rate limit. It costs no agent call.
- Triage, technology cards and their sceptic check read the candidates files (scouting plan WP4).
- Arxiv phrase search can miss work that uses other words for a tag. The tagger's reasons, and the user's own tags, are the place to fix vocabulary.
