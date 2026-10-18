---
name: grill-rc-bootstrap
description: Conduct an evidence-first grilling session that creates a new Research Center (from rc-kit new or a temporary rc_template clone) or migrates existing research material into one - private remote, provider logins, role models, budgets - then hands over to ingest and topic grilling. Use when the user asks to create, set up, bootstrap, configure or migrate a Research Center.
---

# Grill RC bootstrap

First read `BOOTSTRAP.md`. Keep grilling until every step below is verified, not just answered. Ask one decision at a time, with a pick list when the choices are discrete, and recommend an option.

## New RC

1. Determine `template_root` and `target_root` as described in `BOOTSTRAP.md`. If the RC was created with `rc-kit new`, steps 1–2 are already done.
2. Run the materialization (`./rc_template/rc bootstrap install .`); continue from `target_root`.
3. Record the name in `research-center.json`, and set the status to `adapting`.
4. **Purpose**: is this RC for a company (repos, Notion, Drive) or for a person (articles, papers, books)? What decisions should its research feed? This steers the ingest plan and the profile.
5. **Private remote**: the RC commits the text of everything it ingests, so its remote must be private.
   - The user creates the repo, or you run `gh repo create <owner>/<name> --private` after they confirm the owner and name.
   - Then `git remote add origin <url>`.
   - A non-GitHub remote can't be checked. The user confirms it is private, and only then do you set `"privateRemoteConfirmed": true`.
   - No remote yet is allowed: nothing is published.
6. **Logins and models**:
   - `./rc doctor` shows Python, git, uv, gh and the claude and codex logins. The RC stores no credentials.
   - `./rc settings` shows each role and its pipeline slot. Ask which subscriptions the user has. Move roles off a missing provider with `./rc roles set <role> --provider ... --model ...`.
   - Every default role runs on Claude (Opus and Sonnet). Codex roles work only on macOS, Linux or WSL, because its read-only sandbox cannot read files on native Windows. The connector reader needs claude.
   - Notion and Drive ingest need those claude.ai connectors to be connected for the user's Claude account (`claude mcp list`).
7. **Budgets and limits**: agree `budget.ingestCalls`, `budget.researchCalls`, `budget.refreshCalls`, `ingest.maxSourceBytes`, `research.maxSourcesPerResearcher`, `research.resultsPerQuery` and `research.snowballDepth` (0 turns snowballing off). A run that hits a budget stops and can resume.
8. **Sources**:
   - `./rc sources list` shows the adapters every topic can use.
   - `./rc sources packs` shows the domain packs. Enable the ones the RC's purpose calls for (`./rc sources enable medicine`, `software`).
   - OpenAlex and Crossref serve requests faster when they know a contact email. Ask whether the user wants to share one, and set `research.contactEmail` only if they say yes. The default is none.
9. **Living topics**: explain that a topic with a cadence is refreshed with `./rc research refresh --due`. Offer to schedule it (cron or Task Scheduler, GUIDE.md) once the first living topic exists.
10. Replace the template README with this RC's purpose. Keep `GUIDE.md`, `install/`, `CLAUDE.md` and `.claude/skills`: they are the entry point for people and AI tools.
11. `./rc agents sync`, `./rc check`, set the status to `ready`, and commit with the user's go-ahead.
12. **First profile**: the RC works for profiles, each with its own type, tags, sources and topics (for example the company, or the user personally). Create the first with the grill-profile skill and set it as `defaultProfile` in research-center.json if the user will mostly work in it.
13. Hand over: point the profile at the user's material (rc-ingest), or grill a first topic (grill-research-topic)?

## Migration

1. Do not change any files before a read-only inventory of the existing material: notes, reading lists, knowledge bases, earlier reports, bookmarks.
2. Map each item to an ingest source kind (folder, git, url, notion, gdrive), or mark it `drop` with a reason the user agrees to.
3. Materialize the RC next to the material, never into it, and follow the New RC steps.
4. Bring the material in as sources with `./rc ingest add`, one slice at a time. Check each slice's digest and profile notes with the user before the next.
5. Never copy old notes into `knowledge/` or `research/` by hand. Those folders are generated and cited.
6. Keep the old material until the user has checked the profile built from it.

## Acceptance

- `research-center.json` is valid, with status `ready`.
- The remote is private or absent, verified, not assumed.
- Every pipeline role runs on a logged-in provider.
- `./rc check` passes.
- The RC does not depend on `rc_template`.
