---
id: debt.index
title: Tech debt
status: active
summary: Known shortcuts of RC v1 and the conditions for removing them.
verified_at: 2026-10-09
evidence:
  - scripts/ingest/ingest.py
relations:
  - docs/index.md
---

# Tech debt

- [Connector documents are transcribed by a model](connector-transcription.md)
- [Cursor roles cannot search the web](cursor-no-web.md)
- [Flake checks copy the whole instance into the store](flake-check-copies-instance.md)
