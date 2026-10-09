---
id: debt.connector-transcription
title: Notion and Drive documents are transcribed by a model, and re-read on every run
status: active
summary: The connector reader copies documents through the claude.ai connectors, so the stored text can deviate from the original, and change detection needs a fetch (one agent call per connector source per run).
verified_at: 2026-10-09
evidence:
  - scripts/ingest/ingest.py
  - .agents/skills/ingest-connector/SKILL.md
relations:
  - docs/decisions/0002-committed-extracted-sources.md
  - docs/debt/index.md
---

# Notion and Drive documents are transcribed by a model, and re-read on every run

## Statement

The RC holds no Notion or Google credentials, so it reads these through headless Claude and the user's claude.ai connectors. The model is told to reproduce documents verbatim, but nothing proves it did. Without a cheap "last edited" check, each run re-reads every connector source.

## Removal condition

Replace it with direct API exports (a Notion integration token, Drive API OAuth) held in an external secret manager, once the user wants to manage those credentials. Or replace it once the connectors expose raw content and modification times that the runner can read without a model.
