---
name: rc-ingest
description: Point the Research Center at what the user already knows - local folders, Git repos, web pages, Notion, Google Drive - and run ./rc ingest to commit their text, digest each source and build the cited profile. Use when the user wants to add knowledge, point the RC at folders, repos, docs, Notion or Drive, refresh sources, see what was ingested or rebuild the profile.
---

# Ingest knowledge

Ingest is optional and repeatable. It turns sources into committed text (sources/), one digest per source (knowledge/digests/) and a cited profile (knowledge/profile/). Grilling and research read the profile, so the user is never asked what their own material already answers.

## Steps

1. **Collect what to point at.** Ask the user which sources hold their context, and offer the kinds:
   - `folder`: local documents, PDFs, books, slides, article dumps. A Windows path is reachable from WSL as `/mnt/c/...`.
   - `git`: repos, as a local path or a clone URL.
   - `url`: one or more web pages or PDFs.
   - `notion`: page URLs, or `search:<query>`.
   - `gdrive`: document or folder URLs, or `search:<query>`.

   Ask what each source is and why it matters. That goes into `--note` and steers the digest.
2. **Register each source:**
   `./rc ingest add <kind> <locator...> [--id <id>] [--include '<glob>'] [--exclude '<glob>'] [--note "..."]`
   For big repos, narrow with `--include` (for example `docs/*`, `src/*`, `*.md`) before running. The run refuses a source over `ingest.maxSourceBytes`.
3. **Run it in the background, and follow it with `./rc watch`:**
   `./rc ingest run [ids...]`. Relay fetches, redactions, digests, stalls and the result as they happen.
   - The first run on a new instance stops if `origin` is public or its visibility can't be checked. Never work around that: the user makes the repo private, or confirms a non-GitHub remote with `privateRemoteConfirmed`.
   - The budget (`budget.ingestCalls`) caps agent calls. When it is reached, finished sources are kept, and re-running resumes. Raise it only when the user agrees (`--budget N`).
4. **Report** what was fetched, what was skipped and why, the redactions (sources/<id>/redactions.md: tell the user to rotate any real credential listed), and the profile's notes grouped by kind. Point to knowledge/profile/index.md.
5. **Validate and commit** only when the user asks: `./rc validate`, then commit sources/, knowledge/ and catalog/.

## Rules

- Commit only into a private instance. The template never holds data.
- Never paste source content into chat beyond short quotes; the files are in the repo.
- `./rc ingest list` shows the sources and whether each digest is fresh. `./rc ingest remove <id>` drops a source and its text, then `./rc ingest run --profile` rebuilds the profile.
- Notion and Drive are read by headless Claude through the user's claude.ai connectors, with reading tools only. If a connector is missing, the user connects it in claude.ai. The RC never asks for a token.
