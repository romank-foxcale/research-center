---
id: decision.0013-use-case-scopes
title: An RC holds use cases - scoped folders with their own scope, sources, profile and research, sharing the instance's config
status: superseded
summary: usecases/<id>/ holds a scope.md and the data of one use case laid out like an instance's (catalog/sources, sources, knowledge, research); the runners take it as their data root while settings, roles, adapters, templates and skills resolve from the instance; rc -u <id> (or RC_USE_CASE, defaultUseCase, the only one) picks it; research needs an accepted scope and every role reads it first.
verified_at: 2026-10-16
evidence:
  - scripts/profiles.py
  - scripts/profiles_test.py
  - scripts/runner/rc.py
  - rc.py
  - templates/scope.md
  - docs/decisions/0015-profiles.md
relations:
  - docs/decisions/0015-profiles.md
  - docs/decisions/0001-template-and-instances.md
  - docs/decisions/0012-windows-native-uv.md
  - docs/architecture/research-center.md
---

# An RC holds use cases - scoped folders with their own scope, sources, profile and research, sharing the instance's config

Superseded on 2026-10-18 by [0015 Profiles](0015-profiles.md): use cases became profiles with a type, tags and an optional scope.

## Context

One RC serves more than one purpose. Examples are foxcale's products (DI, PV, CA) and the user's own interests later. Research for one must be judged against that purpose's products, constraints and value, and must not draw on the other's material. On 2026-10-16 the user chose to keep these as namespaces inside one instance rather than as separate instances, and named the first use case `foxcale`. Plan: plans/active/use-case-scopes.md.

## Decision

- **A use case is a folder laid out like a small instance.** `usecases/<id>/` holds:
  - `usecase.json` (id, title, createdAt);
  - `scope.md`, from `templates/scope.md`;
  - `catalog/sources/`, `sources/`, `knowledge/`, `research/`;
  - its own ignored `.rc-local/`.

  The ingest and research runners take that folder as their data root, unchanged.
- **Config stays shared.** `rc.instance(path)` walks up to `research-center.json`. Settings, roles, adapters, evidence types, templates and skills resolve from there, so one set of roles and adapters serves every use case.
- **Agents run in the use-case folder.** Their relative paths (`scope.md`, `research/<topic>/`, `knowledge/profile/`, `sources/`) resolve inside it, so a run reads only its own use case's material.
- **Selection:** `rc -u <id> <command>` for ingest, research and watch. Without `-u`, the order is `RC_USE_CASE`, then `defaultUseCase` in research-center.json, then the only use case there is. Several use cases without a choice is an error, never a guess. `rc research refresh --due` without `-u` refreshes every use case. An instance without `usecases/` works as before, with its root as the data root.
- **The scope gates research.** `scope.md` has seven sections:
  - Who;
  - Products and processes, with the components a new technology could plug into;
  - Hard constraints;
  - How value is measured;
  - Out of scope;
  - Scouting lens;
  - Source preferences.

  It goes from draft to accepted (`rc usecase accept`, which needs every section filled). Research and refresh in a use case refuse to run until its scope is accepted. Every research role's context names `scope.md` first. The planner applies its lens and source preferences; the applier names the product and component an idea would change and estimates value in the scope's measures.
- **Checks:** the validator checks every use case: `usecase.json`, an accepted scope's sections, and its sources, notes, reports and secrets. Markdown under `usecases/` is allowed. The template ships no use case: a scope is private data.

## Consequences

- `rc usecase new|list|show|accept` manages use cases. The `grill-use-case` skill writes a scope evidence-first.
- Adapters and packs are shared. A use case steers them through its source preferences until per-use-case packs are needed.
- Moving a topic between use cases means moving its folder and the sources it cites, by hand.
