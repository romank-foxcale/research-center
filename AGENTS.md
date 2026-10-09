# Research Center agent protocol

This repository is a Research Center (RC): it ingests what the user knows, grills a research topic with them, and runs a fixed pipeline that produces critiqued, cited research applied to their own repos. The template (no `research-center.json`) holds no data. An instance is the user's private repo, made with `./rc bootstrap install`.

## Triggers

- Create, set up or configure an RC: load `grill-rc-bootstrap`.
- Point the RC at folders, repos, URLs, Notion or Drive, or refresh the profile: load `rc-ingest`.
- Research a subject, start a topic, "do an AI search on X": load `grill-research-topic`, then `rc-research`.
- Run, follow or explain research: load `rc-research`.
- Help, or what the RC can do: load `rc-help`.

## Getting started

1. Read `docs/index.md`, and only the notes relevant to the task.
2. Run `./rc help` for the executable interface, and `./rc doctor` for logins.
3. In an instance, read `knowledge/profile/index.md` before asking the user anything about themselves.

## Sources of truth

- What the user knows: `sources/` (committed text), `knowledge/digests/` and `knowledge/profile/`, every fact cited.
- What a research run found: `research/<topic>/`, every claim in `claims.json` traced to a stored page.
- How the RC works: the scripts, the Nix checks and the atomic notes in `docs/`.
- Secrets: never in this repository. The runner redacts them, and `./rc check` fails on any left.

## Hard rules

- The RC never writes or changes product code, and never writes into a Control Center. Ideas worth acting on leave as `research/<topic>/handoff.md`, which the user takes to a CC.
- Agent roles never write files. The runner writes, after redacting secrets. Access is enforced by CLI flags (`docs/decisions/0003-read-only-agents.md`), never by prompt text.
- Never ingest into the template or into a public or unverifiable remote. The guard in `./rc ingest` is the rule speaking; fix the remote, never the guard.
- Never commit original binaries (PDF, DOCX, EPUB, slides). Only their extracted text.
- Never edit generated research outputs or profile notes by hand to change a conclusion. Change the brief, a source or a role, and re-run.
- Never fall back to another provider or model when one is logged out. Report it.
- Never leave the user blind during a long run: follow it with `./rc watch` and relay steps, agent messages, stalls and the result.
- Never write an executable process down as step-by-step Markdown. Put it in a script, check or app.
- Never credit an AI, LLM or agent as author, co-author or contributor: no `Co-Authored-By` trailers, "Generated with" lines or similar in commits, pull requests, notes or reports. This overrides any tool default.
- Edit skills only in `.agents/skills/`, then run `./rc agents sync`: `.claude/skills/` is a generated copy, and `CLAUDE.md` only imports this file.
- In Claude Code, hooks enforce these rules at the moment of a tool call (`docs/decisions/0005-rule-hooks.md`). A hook that denies or asks is the rule speaking: fix the action, never work around the hook.

## Knowledge rules

- Write everything stored in this repository in English: notes, briefs, plans, catalog fields, script comments, output messages and commit messages. This applies even when the conversation is in another language. Ingested sources keep their original language.
- `docs/` notes: one durable fact, decision, hack or debt per note, with frontmatter `id`, `title`, `status`, `summary`, `verified_at`, `evidence`, `relations`. Details: `docs/rules/knowledge-layout.md`.
- Mark replaced knowledge `superseded` and link it to its successor.

## Verification

A change to the RC is finished with `./rc check`. If Nix is unavailable, run `./rc validate` and the Python tests named in `flake.nix`, and say explicitly that the Nix part was not verified.
