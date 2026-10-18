---
id: architecture.research-center
title: Research Center architecture
status: active
summary: The RC is a runner that drives read-only agent roles through ingest (fetch, digest, profile), scouting (discover, triage, technology cards, challenge) and research (plan, search, screen, collect, analyze, critique, judge, apply, report) for profiles; every file is written by the runner and every fact is traced to stored text.
verified_at: 2026-10-18
evidence:
  - scripts/runner/rc.py
  - scripts/ingest/ingest.py
  - scripts/research/research.py
  - templates/research-center.json
  - scripts/sources/sources.py
  - scripts/research/living.py
  - scripts/scout/scout.py
  - scripts/scout/cards.py
  - scripts/profiles.py
relations:
  - docs/decisions/0001-template-and-instances.md
  - docs/decisions/0003-read-only-agents.md
  - docs/decisions/0004-research-pipeline.md
  - docs/decisions/0015-profiles.md
  - docs/decisions/0016-scouting.md
---

# Research Center architecture

## Layout of an instance

| Path | Holds | Written by |
| --- | --- | --- |
| research-center.json | budgets (ingest, research, refresh), ingest limits, research settings (results per query, screening batch, snowballing, contact email), scout settings (sources, results per query, cards per run, calls, cadence), which role fills which pipeline slot, the default profile | the user (bootstrap) |
| catalog/agents/ | one JSON per role: provider, model, access, skills | the user (`./rc roles set`) |
| catalog/evidence-types.json | the evidence types with their reliability ceiling and half-life | the template (seeded), the user |
| catalog/adapters/ | one JSON per enabled source adapter: family, what it covers, filters, rate limit; code/ holds the instance's own adapters and fixtures | the template (seeded), `./rc sources enable` and `new`, the user |
| profiles/&lt;id&gt;/ | one profile: profile.json (name, description, type, tags), an optional scope.md, inbox/, and its own catalog/sources/, sources/, knowledge/ and research/ laid out as below (docs/decisions/0015-profiles.md) | `rc profile new`, grill-profile, the runners |
| profiles/&lt;id&gt;/scout/ | candidates/ per discovery, seen.json (every find once: candidate, passed, card, dismissed), state.json (last discovery, last run), evidence/ (stored READMEs and paper pages), cards/ (technology cards, JSON and Markdown) (docs/decisions/0016-scouting.md) | scout runner |
| trends/ | the shared trends feed, laid out like a profile (profile.json with general tags, scout/), judged against every profile | `rc trends` |
| templates/licences.json | SPDX licences by class, and why each unusable class is unusable for a company profile | the template |
| catalog/sources/ | one JSON per source: kind, locators, include/exclude, note (in a profile, its own) | `./rc ingest add`, research collect |
| sources/&lt;id&gt;/ | extracted text, manifest (origin, sha256, extractor), redactions | ingest runner |
| knowledge/digests/ | one cited digest per user source, with the manifest fingerprint | ingest runner (digester role) |
| knowledge/profile/ | atomic cited notes about the user or company, and an index | ingest runner (profiler role) |
| research/&lt;topic&gt;/ | brief, source plan, searches, candidates, screening and citations, claims ledger, analysis with its assumptions and matrices, critique, judgement with credibility and certainty, fit, report, handoff; for a living topic watch.json and delta/ | grilling session, research runner |
| .rc-local/ | event streams, agent logs, git clone cache, reviewer mapping, accepted replies of unfinished stages, refresh snapshots, report pages and their share links in reports/ (ignored) | runners, `rc report` |

## Flow

1. **Profile**: `rc profile new` or the grill-profile skill creates `profiles/<id>/` with a type (which sets the licence rule) and a description; `rc tags` adds interest tags, or proposes them from the profile's material (tagger role). The steps below run inside one profile (`rc -p <id>`).
2. **Ingest** (`scripts/ingest/ingest.py`): each source is fetched by kind. Folders and repos are read by the runner, URLs are downloaded, and Notion and Drive are read by the connector role. Text is extracted (`extract.py`), redacted (`secrets_scan.py`) and stored with a manifest. A source whose manifest fingerprint changed is digested in chunks; then the profiler rebuilds the profile from all digests.
3. **Scout** (`scripts/scout/`): discovery per tag across the adapters with no agent; triage (one call) picks the finds worth a card; the runner stores each pick's evidence and sets its licence verdict; the evaluator writes a technology card per pick, quoting the evidence; the sceptic reviews every card; `rc scout --due` runs it weekly, `rc trends` for the shared feed, and `rc scout dive` turns a card into a draft brief (docs/decisions/0016-scouting.md).
4. **Grill** (for a deep dive): an interactive session follows `grill-research-topic`, reads the profile, and writes and accepts the brief.
5. **Research** (`scripts/research/research.py`): nine stages, each committing its output. Search runs the planned adapter queries without an agent; screen includes or excludes every result with a logged reason (docs/decisions/0008-search-and-screen.md). The runner checks every reply against the stage's contract and gives the role one retry with the problems listed.
6. **Refresh** (`scripts/research/living.py`): stored pages past their evidence type's half-life are re-checked for drift; a living topic's saved searches re-run since the last check; only new records are screened and collected; and the conclusions are re-derived when new verified evidence arrives or relied-on evidence drifted (docs/decisions/0009-living-topics.md, 0010-evidence-grading.md).
7. **Share** (`scripts/report/`, rc-share): `rc home` renders the main screen (every profile's cards, a page per card, the trends feed), and `rc report` a topic or a profile's research dashboard, into self-contained HTML from the committed outputs, with no agent call; the rc-share skill publishes it as a private artifact after the user confirms (docs/decisions/0014-report-pages.md).

## Runtime

- `scripts/runner/rc.py`: settings, roles, the call budget, checked and parallel calls that keep every accepted reply until their stage commits, and the event stream `./rc watch` follows.
- `scripts/runner/providers.py`: one headless CLI call per role, with access enforced by flags.
- `scripts/sources/`: source adapters the runner searches besides the web (`./rc sources`), one record shape keyed by DOI or canonical URL, every search logged; domain packs in `templates/packs/`, the scaffold for an instance's own adapters in `templates/adapter-template/` (docs/decisions/0007-source-adapters.md).
- `scripts/research/research.py`: the pipeline and its contracts: plan, screening, grading (0010), competing hypotheses and calibrated language (0011). `living.py`: watch, refresh, drift and deltas (0009).
- `rc.py` with the `rc.cmd`, `rc.ps1` and `./rc` launchers: the command line, run by uv in the environment of `pyproject.toml` and `uv.lock`. Document conversion is pure Python (pypdfium2, mammoth, markdownify, striprtf, python-pptx, openpyxl), so nothing else is installed (docs/decisions/0012-windows-native-uv.md).
- `scripts/profiles.py`, `scripts/tags.py`, `scripts/runner/licences.py`: profiles, interest tags and the licence rule (0015).
- `scripts/scout/scout.py`: discovery per interest tag, the seen-list and candidates, the schedule, deep dives and the trends feed; `cards.py`: triage, technology cards and their challenge (0016).
- `scripts/report/home.py`: the main screen and card pages (0014).
- `scripts/report/report.py`: report pages and the dashboard, share copies and recorded share links (0014).
- `scripts/upgrade-instance.py` (`rc upgrade`, `rc-kit upgrade`): brings an existing instance's template-owned files up to the template.
