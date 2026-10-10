---
id: decision.0007-source-adapters
title: Structured sources are searched by runner-side adapters, chosen per topic from their descriptors
status: accepted
summary: Besides web search by the researcher roles, the runner queries source adapters (scripts/sources/adapters/) described in catalog/adapters/*.json; every adapter returns one record shape keyed by DOI or canonical URL, needs no stored credential, logs each search, and is tested offline against fixtures.
verified_at: 2026-10-10
evidence:
  - scripts/sources/kit.py
  - scripts/sources/sources.py
  - scripts/sources/sources_test.py
  - templates/adapters/openalex.json
relations:
  - docs/decisions/0003-read-only-agents.md
  - docs/decisions/0004-research-pipeline.md
  - docs/architecture/research-center.md
---

# Structured sources are searched by runner-side adapters, chosen per topic from their descriptors

## Context

Collection by web search alone favours whatever ranks well and misses scholarly databases, feeds, news archives and catalogues. The RC must work for any subject, not only software. So the sources cannot be a fixed list: each topic needs the ones that fit it. Plan: plans/active/living-research.md.

## Decision

- **Adapters run in the runner, never in an agent.** `scripts/sources/adapters/<module>.py` exposes `search(query, filters, since, limit, options)` and optionally `related(record, direction, limit, options)` for references (backward) and citations (forward). Roles get no new tools, so ADR 0003 holds unchanged.
- **Descriptors are the planner's menu.** Each `catalog/adapters/<id>.json` (seeded from `templates/adapters/`) declares `family`, `covers` in plain words, `evidenceTypes`, `queryHelp`, allowed `filters`, `watchable`, `related`, `needsKeyEnv` and `rateLimit`. The validator checks each descriptor and that its module exists.
- **One record shape.** `adapter, key, title, authors, date, url, doi, evidenceType, abstract, extra`. The `key` is `doi:<doi>` when there is one, else `url:<canonical url>`. A canonical URL keeps the path and the query, minus tracking parameters, so different pages never merge. Malformed results are skipped one by one, never the whole search.
- **Every search is logged** with its adapter, exact query, filters, since, limit, time, status and count (PRISMA-S), and an error is logged and raised, never swallowed into an empty result.
- **No stored credentials and no unasked disclosure.** The default adapters need no key. An adapter that needs one reads it from the environment variable its descriptor names. The polite-pool contact email goes to OpenAlex and Crossref only when the user sets `research.contactEmail`.
- **Polite and safe HTTP.** One request per `rateLimit` seconds per host, retries on 429 and 5xx, a 10 MB response cap, and XML with entity declarations is refused.
- **The default set works for any topic:** openalex, crossref, wikipedia, openlibrary, gdelt, feed (any RSS or Atom URL) and page-watch (a fingerprinted page). Domain packs add adapters without changing the core.
- **Tests never touch the network.** `sources_test.py` replays synthetic fixtures shaped like the real responses (`scripts/sources/fixtures/`).

## Consequences

- `./rc sources list|search|related` works in the template and in instances, with no Nix closure (standard library only).
- Evidence types are a provisional constant in `kit.py`; the grading plan moves them to an editable catalog.
- page-watch fingerprints the whole visible page text, so pages with rotating content (banners, dates) change on every check. Narrowing to a page region is left until a topic needs it.
