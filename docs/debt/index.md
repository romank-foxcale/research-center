---
id: debt.index
title: Tech debt
status: active
summary: Known shortcuts of RC v1 and the conditions for removing them.
verified_at: 2026-10-11
evidence:
  - scripts/ingest/ingest.py
relations:
  - docs/index.md
---

# Tech debt

- [Connector documents are transcribed by a model](connector-transcription.md)
- [Cursor roles cannot search the web](cursor-no-web.md)
- [Flake checks copy the whole instance into the store](flake-check-copies-instance.md)
- [Instances do not receive template updates](instance-updates.md)
- [page-watch fingerprints the whole visible page](page-watch-whole-page.md)
- [A refresh searches less than a full run](refresh-coverage.md)
- [Grades and language are checked for form, not truth](checks-of-form.md)
