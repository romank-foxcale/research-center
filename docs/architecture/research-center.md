---
id: architecture.research-center
title: Research Center architecture
status: active
summary: The RC is a runner that drives read-only agent roles through ingest (fetch, digest, profile) and research (plan, collect, analyze, critique, judge, apply, report); every file is written by the runner and every fact is traced to stored text.
verified_at: 2026-10-09
evidence:
  - scripts/runner/rc.py
  - scripts/ingest/ingest.py
  - scripts/research/research.py
  - templates/research-center.json
relations:
  - docs/decisions/0001-template-and-instances.md
  - docs/decisions/0003-read-only-agents.md
  - docs/decisions/0004-research-pipeline.md
---

# Research Center architecture

## Layout of an instance

| Path | Holds | Written by |
| --- | --- | --- |
| research-center.json | budgets, ingest limits, which role fills which pipeline slot | the user (bootstrap) |
| catalog/agents/ | one JSON per role: provider, model, access, skills | the user (`./rc roles set`) |
| catalog/sources/ | one JSON per source: kind, locators, include/exclude, note | `./rc ingest add`, research collect |
| sources/&lt;id&gt;/ | extracted text, manifest (origin, sha256, extractor), redactions | ingest runner |
| knowledge/digests/ | one cited digest per user source, with the manifest fingerprint | ingest runner (digester role) |
| knowledge/profile/ | atomic cited notes about the user or company, and an index | ingest runner (profiler role) |
| research/&lt;topic&gt;/ | brief, source plan, claims ledger, analysis, critique, judgement, fit, report, handoff | grilling session, research runner |
| .rc-local/ | event streams, agent logs, git clone cache, reviewer mapping (ignored) | runners |

## Flow

1. **Ingest** (`scripts/ingest/ingest.py`): each source is fetched by kind. Folders and repos are read by the runner, URLs are downloaded, and Notion and Drive are read by the connector role. Text is extracted (`extract.py`), redacted (`secrets_scan.py`) and stored with a manifest. A source whose manifest fingerprint changed is digested in chunks; then the profiler rebuilds the profile from all digests.
2. **Grill**: an interactive session follows `grill-research-topic`, reads the profile, and writes and accepts the brief.
3. **Research** (`scripts/research/research.py`): seven stages, each committing its output. The runner checks every reply against the stage's contract and gives the role one retry with the problems listed.

## Runtime

- `scripts/runner/rc.py`: settings, roles, the call budget, checked and parallel calls, and the event stream `./rc watch` follows.
- `scripts/runner/providers.py`: one headless CLI call per role, with access enforced by flags.
- `nix/tools.nix`: pandoc, pdftotext, python-pptx and openpyxl for ingest and collect. It is built from that file alone, so a large instance is not copied into the store on every command.
