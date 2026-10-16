---
name: grill-use-case
description: Create a use case in the Research Center and grill the user, evidence-first, until its scope is accepted - whom it serves, the products and processes with the components a new technology could plug into, hard constraints, how value is measured, out of scope, the scouting lens and source preferences. Use when the user wants a new use case (a company, a product line, a personal area of interest), or to write, review or change a use case's scope.
---

# Grill a use case

A use case is one scoped part of the RC: `usecases/<id>/`, with its own sources, profile and research. Its scope (`scope.md`) is what every research run in it is judged against. A vague scope gives generic research, so ground every line in evidence.

## 1. Create it

`./rc usecase new <id> --title "<title>"` creates `usecases/<id>/` with a draft `scope.md` from `templates/scope.md`. Ids are lowercase hyphen-case: `foxcale`, `personal`.

## 2. Gather evidence before asking

Read what already describes the subject, then state it back instead of asking:

- The use case's profile (`usecases/<id>/knowledge/profile/index.md`) when its sources were ingested (`./rc -u <id> ingest ...`, rc-ingest skill).
- Material the user points at: a company website, product repos or their Control Centers, specs and plans. Read them; never copy secrets. If you find credentials or keys in what you read, tell the user where, and don't quote them.
- For each fact, keep where it came from (a file path or URL), and put it in the scope after the fact, in brackets.

## 3. Grill, one section at a time

Use a pick list when the choices are discrete. Recommend an option and say why.

1. **Who**: the organisation or person, what they do, their market and situation.
2. **Products and processes**: one block per product or process: what it is, users, stack, main stages. For each, the components where new technology could plug in or replace something. Ask which components hurt most.
3. **Hard constraints**: data residency, offline or air-gapped operation, languages, licences, hosting, privacy and compliance, cost ceilings, platform limits. A recommendation that breaks one is worthless, so get them all.
4. **How value is measured**: the metrics and business levers, with the user's own numbers where they exist.
5. **Out of scope**: what research must not spend effort on.
6. **Scouting lens**: the capability areas worth watching, each tied to the component it would serve.
7. **Source preferences**: sources and packs that fit (`./rc sources packs`), feeds or pages to watch, sources to distrust, languages.

Challenge answers that would make research unfocused ("anything AI") or unfalsifiable.

## 4. Write and accept

- Edit `usecases/<id>/scope.md`: replace every `<placeholder>`, keep the headings and the `Use case:` and `Status:` lines.
- Show the user the scope and change it until they agree.
- `./rc usecase accept <id>` checks it (every section filled) and marks it accepted. Research in the use case runs only against an accepted scope.
- Then offer the next step: ingest the use case's material (rc-ingest, with `./rc -u <id>`), or grill a first research topic (grill-research-topic).

Never accept a scope the user has not agreed to. To change an accepted scope later, edit it with the user. Research already run stays as it was until its topics are re-run.
