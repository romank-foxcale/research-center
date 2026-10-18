---
id: architecture.research-center
title: Research Center architecture
status: active
summary: The RC is a runner that drives read-only agent roles through ingest (fetch, digest, profile) and research (plan, search, screen, collect, analyze, critique, judge, apply, report); every file is written by the runner and every fact is traced to stored text.
verified_at: 2026-10-18
evidence:
  - scripts/runner/rc.py
  - scripts/ingest/ingest.py
  - scripts/research/research.py
  - templates/research-center.json
  - scripts/sources/sources.py
  - scripts/research/living.py
relations:
  - docs/decisions/0001-template-and-instances.md
  - docs/decisions/0003-read-only-agents.md
  - docs/decisions/0004-research-pipeline.md
---

# Research Center architecture

## Layout of an instance

| Path | Holds | Written by |
| --- | --- | --- |
| research-center.json | budgets (ingest, research, refresh), ingest limits, research settings (results per query, screening batch, snowballing, contact email), which role fills which pipeline slot | the user (bootstrap) |
| catalog/agents/ | one JSON per role: provider, model, access, skills | the user (`./rc roles set`) |
| catalog/evidence-types.json | the evidence types with their reliability ceiling and half-life | the template (seeded), the user |
| catalog/adapters/ | one JSON per enabled source adapter: family, what it covers, filters, rate limit; code/ holds the instance's own adapters and fixtures | the template (seeded), `./rc sources enable` and `new`, the user |
| profiles/&lt;id&gt;/ | one profile: profile.json (name, description, type, tags), an optional scope.md, inbox/, and its own catalog/sources/, sources/, knowledge/ and research/ laid out as below (docs/decisions/0015-profiles.md) | `rc profile new`, grill-profile, the runners |
| catalog/sources/ | one JSON per source: kind, locators, include/exclude, note (in a profile, its own) | `./rc ingest add`, research collect |
| sources/&lt;id&gt;/ | extracted text, manifest (origin, sha256, extractor), redactions | ingest runner |
| knowledge/digests/ | one cited digest per user source, with the manifest fingerprint | ingest runner (digester role) |
| knowledge/profile/ | atomic cited notes about the user or company, and an index | ingest runner (profiler role) |
| research/&lt;topic&gt;/ | brief, source plan, searches, candidates, screening and citations, claims ledger, analysis with its assumptions and matrices, critique, judgement with credibility and certainty, fit, report, handoff; for a living topic watch.json and delta/ | grilling session, research runner |
| .rc-local/ | event streams, agent logs, git clone cache, reviewer mapping, accepted replies of unfinished stages, refresh snapshots, report pages and their share links in reports/ (ignored) | runners, `rc report` |

## Flow

1. **Profile**: `rc profile new` or the grill-profile skill creates `profiles/<id>/` with a type (which sets the licence rule), a description and tags. The steps below run inside one profile (`rc -p <id>`).
2. **Ingest** (`scripts/ingest/ingest.py`): each source is fetched by kind. Folders and repos are read by the runner, URLs are downloaded, and Notion and Drive are read by the connector role. Text is extracted (`extract.py`), redacted (`secrets_scan.py`) and stored with a manifest. A source whose manifest fingerprint changed is digested in chunks; then the profiler rebuilds the profile from all digests.
3. **Grill**: an interactive session follows `grill-research-topic`, reads the profile, and writes and accepts the brief.
4. **Research** (`scripts/research/research.py`): nine stages, each committing its output. Search runs the planned adapter queries without an agent; screen includes or excludes every result with a logged reason (docs/decisions/0008-search-and-screen.md). The runner checks every reply against the stage's contract and gives the role one retry with the problems listed.
5. **Refresh** (`scripts/research/living.py`): stored pages past their evidence type's half-life are re-checked for drift; a living topic's saved searches re-run since the last check; only new records are screened and collected; and the conclusions are re-derived when new verified evidence arrives or relied-on evidence drifted (docs/decisions/0009-living-topics.md, 0010-evidence-grading.md).
6. **Share** (`scripts/report/report.py`, rc-share): `rc report` renders a topic, or the profile's dashboard, into self-contained HTML from the committed outputs, with no agent call; the rc-share skill publishes it as a private artifact after the user confirms (docs/decisions/0014-report-pages.md).

## Runtime

- `scripts/runner/rc.py`: settings, roles, the call budget, checked and parallel calls that keep every accepted reply until their stage commits, and the event stream `./rc watch` follows.
- `scripts/runner/providers.py`: one headless CLI call per role, with access enforced by flags.
- `scripts/sources/`: source adapters the runner searches besides the web (`./rc sources`), one record shape keyed by DOI or canonical URL, every search logged; domain packs in `templates/packs/`, the scaffold for an instance's own adapters in `templates/adapter-template/` (docs/decisions/0007-source-adapters.md).
- `scripts/research/research.py`: the pipeline and its contracts: plan, screening, grading (0010), competing hypotheses and calibrated language (0011). `living.py`: watch, refresh, drift and deltas (0009).
- `rc.py` with the `rc.cmd`, `rc.ps1` and `./rc` launchers: the command line, run by uv in the environment of `pyproject.toml` and `uv.lock`. Document conversion is pure Python (pypdfium2, mammoth, markdownify, striprtf, python-pptx, openpyxl), so nothing else is installed (docs/decisions/0012-windows-native-uv.md).
- `scripts/scout/scout.py`: discovery per interest tag across the adapters, the seen-list and candidates (0016).
- `scripts/report/report.py`: report pages and the dashboard, share copies and recorded share links (0014).
- `scripts/upgrade-instance.py` (`rc upgrade`, `rc-kit upgrade`): brings an existing instance's template-owned files up to the template.
