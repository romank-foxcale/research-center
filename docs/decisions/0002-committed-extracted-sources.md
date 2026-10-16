---
id: decision.0002-committed-extracted-sources
title: Sources are committed as redacted extracted text, only in a private instance
status: accepted
summary: Ingest commits the text of every source (never original binaries), replaces secrets with markers and reports them, and refuses to run when origin is public or its visibility cannot be checked.
verified_at: 2026-10-09
evidence:
  - scripts/ingest/ingest.py
  - scripts/ingest/extract.py
  - scripts/ingest/secrets_scan.py
  - scripts/validate-research-center.py
relations:
  - docs/decisions/0001-template-and-instances.md
  - docs/debt/connector-transcription.md
---

# Sources are committed as redacted extracted text, only in a private instance

## Context

The user chose to keep everything the RC knows inside the instance repo, so research can be re-checked later without the original systems. Company material often contains credentials, and books and PDFs are large binaries.

## Decision

- Text files are stored as they are, under a `.txt` suffix (Markdown keeps `.md`), so no ingested file can act on Git or the tools. Characters outside `[A-Za-z0-9._/-]` in a path become `_`, so every path can be cited.
- PDF goes through pdftotext; DOCX, ODT, EPUB, RTF and HTML through pandoc (GFM, no raw HTML); PPTX through python-pptx; XLSX through openpyxl (200 rows per sheet). Other binaries are skipped and listed in the manifest.
- Before anything is written, `secrets_scan.redact` replaces token formats (cloud keys, GitHub, Slack, OpenAI, Anthropic, Google, Stripe, JWT, private keys, URL credentials) and credential-looking assignments with `[REDACTED:<kind>]`. `sources/<id>/redactions.md` lists the kind and line, never the value.
- `./rc check` fails on any unredacted pattern under sources/, knowledge/, research/ and catalog/, and on any binary under sources/.
- `./rc ingest` refuses an instance whose GitHub origin is not PRIVATE or INTERNAL according to `gh`, or whose visibility `gh` cannot report. A non-GitHub origin needs `privateRemoteConfirmed`. A repo without a remote is allowed, since nothing is published from it.

## Limits

- The scanner catches known formats and credential-looking assignments, not every secret. The redaction report tells the user to rotate what it found.
- Copyright of committed book and paper text stays the user's responsibility.
