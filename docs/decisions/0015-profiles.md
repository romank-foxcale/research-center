---
id: decision.0015-profiles
title: An RC works for profiles - a company or a person, with a type that sets the licence rule, a description and interest tags
status: accepted
summary: Use cases became profiles. profiles/<id>/ holds profile.json (name, description, type company or personal, interest tags) and the profile's own data laid out like an instance's; the type sets the licence rule (company - permissive only, every other licence flagged; personal - any), classified by the runner from templates/licences.json; scope.md is optional; research needs a description or tags; rc -p <id> (or RC_PROFILE, defaultProfile, the only one) picks it, -u kept as an alias; rc upgrade moves usecases/ to profiles/.
verified_at: 2026-10-18
evidence:
  - scripts/profiles.py
  - scripts/profiles_test.py
  - scripts/runner/licences.py
  - templates/licences.json
  - scripts/upgrade-instance.py
  - rc.py
  - .agents/skills/grill-profile/SKILL.md
relations:
  - docs/decisions/0013-use-case-scopes.md
  - docs/decisions/0001-template-and-instances.md
  - docs/architecture/research-center.md
---

# An RC works for profiles - a company or a person, with a type that sets the licence rule, a description and interest tags

## Context

On 2026-10-18 the user restated what the RC is for. It is a scout for named profiles, such as foxcale or the user personally:
- a profile is written by hand or drawn from dropped material;
- its interests are editable tags;
- whether it is a company or personal decides which licences are usable, because a company that makes money from what it builds cannot use every licence.

Use cases (ADR 0013) had the isolation right, but missed three things. They had no type, so no licence rule. Their interests were buried in a long `scope.md`. And research refused to run without that scope accepted. The user chose to rename them. Plan: plans/active/scouting.md.

## Decision

- **A profile is a folder laid out like a small instance.** `profiles/<id>/` holds:
  - `profile.json`: id, name, description, type, tags and createdAt;
  - `inbox/`, `catalog/sources/`, `sources/`, `knowledge/` and `research/`;
  - its own ignored `.rc-local/`.

  The runners take the folder as their data root. Config resolves from the instance, as under ADR 0013.
- **The type sets the licence rule.**
  - `company`: only the permissive class in `templates/licences.json` is usable (MIT, Apache-2.0, BSD, ISC, MPL-2.0 and similar).
  - `personal`: any licence is usable.

  The runner classifies a licence from its SPDX id (`scripts/runner/licences.py`). An agent never does. An unreadable licence is `unknown`, and an unusable licence is flagged with its reason, never hidden. Research roles read the rule from their context.
- **`scope.md` is optional.** `rc profile scope <id>` starts one, and `rc profile accept <id>` checks it. Research needs only a description or at least one tag, so its results can be judged against whom they serve.
- **Selection:** `rc -p <id>`. Without it, the order is `RC_PROFILE`, then `defaultProfile`, then the only profile there is. `-u`, `RC_USE_CASE` and `defaultUseCase` still work for one release.
- **Migration:** `rc upgrade` moves `usecases/<id>/` to `profiles/<id>/` with `git mv`, so history follows. In the move:
  - `usecase.json` becomes `profile.json`: the title is the name, and the scope's first Who paragraph is the description;
  - `defaultUseCase` becomes `defaultProfile`;
  - a migrated profile is a company profile, the stricter rule, until the user changes it.

  The validator and `rc` refuse a leftover `usecases/` folder.

## Consequences

- `rc profile new|list|show|edit|scope|accept` and the `grill-profile` skill replace `rc usecase` and `grill-use-case`.
- "Profile notes" (`knowledge/profile/`, built by ingest) are the profile's knowledge. "Profile" alone means the profile itself.
- Interest tags, scouting and technology cards build on `profile.json` (plans/active/scouting.md).
