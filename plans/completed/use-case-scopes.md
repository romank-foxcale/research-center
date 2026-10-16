# use-case-scopes: An RC holds several use cases, each with its own scope, sources, profile and research

Lifecycle: completed
Planning status: accepted

## Outcome

One RC instance holds named **use cases**. The first is `foxcale` (the company and its products); a personal one comes later. Each use case:

- has a **scope** (`usecases/<id>/scope.md`): who it serves, its products and processes with the points where new technology could plug in, hard constraints, how value is measured, what is out of scope, the lens for scouting (capability areas), and preferred sources;
- has **its own data**: ingested sources, digests and profile, research topics and their outputs, all under `usecases/<id>/`, never mixed with another use case's;
- gives every research run the scope as context, so plans, screening, analysis and fit are judged against that use case's products and constraints.

Settings, roles, adapters, evidence types, skills and scripts stay shared by the whole instance.

## Non-goals

- Technology scouting (the continuous catalog of candidate technologies): the next plan, which builds on use cases.
- Per-use-case adapters or roles: shared for now; a scope steers the planner through its source preferences.
- The personal use case: out of scope until the user asks.

## Evidence and current behavior

- The user decided on 2026-10-16:
  - option 1, a use case is a namespace inside one instance;
  - the first use case is `foxcale`, and the draft scope from the session is good enough to start.
- Data code takes one `root` and uses `root/catalog/sources`, `root/sources`, `root/knowledge`, `root/research` and `root/.rc-local`, about 20 uses.
- Config code uses `root/research-center.json`, `root/catalog/{agents,adapters,evidence-types.json}`, `root/templates` and `root/.agents`, about 80 uses.
- Sources for the foxcale scope:
  - foxcale.com (homepage, read 2026-10-16);
  - read-only surveys of `di_CC` (foxcope-DI / Inspector 2.0) and `pv_CC` (foxcope-PV) with file-path evidence, done in this session.
- Security finding to pass on, not to act on: `di_CC/.notes/di/00-index.md` notes a private key and a VPN profile in a shared Drive folder.

## Affected scope

| Repository | Worktree | Read/write | Interfaces |
| --- | --- | --- | --- |
| research-center | local clone | write | `rc usecase ...`, `rc -u <id> ...`, `scripts/runner/rc.py`, `scripts/research/`, `scripts/ingest/`, `scripts/sources/`, validators, hooks, `templates/scope.md`, skills |
| foxcale_RC (new instance) | `%USERPROFILE%\Projects\foxcale_RC` | write | `usecases/foxcale/` |

## Invariants and decisions

- **A use case is a small instance.** `usecases/<id>/` holds:
  - `usecase.json` (id, title, status);
  - `scope.md`;
  - `catalog/sources/`, `sources/`, `knowledge/`, `research/`;
  - its own ignored `.rc-local/`.

  Data code runs unchanged with the use-case folder as its root. Config lookups resolve the instance by walking up to `research-center.json`.
- **Agents run in the use-case folder.** Their relative paths (`research/<topic>/brief.md`, `knowledge/profile/index.md`, `sources/...`) resolve inside it, so a run sees only its own use case's material.
- **Selecting a use case:** `rc -u <id> <command>`, else `RC_USE_CASE`, else `defaultUseCase` in research-center.json, else the only one there is. An instance without `usecases/` keeps working as before: its root is the data root.
- **Scope lifecycle:** draft, then accepted, like a brief. `rc usecase accept` checks that every section is filled. Research in a use case requires an accepted scope.
- **The template ships no use case**, because a scope is private data like any other.

## Open questions

| Question | Impact | Owner/next evidence |
| --- | --- | --- |
| Should packs and adapters become per use case? | A medical use case and a software one want different packs | Decide when a second real use case exists |

## Work packages

| ID | Outcome | Write scope | Depends on | Completion check |
| --- | --- | --- | --- | --- |
| WP1 | Instance resolution for config; use-case folders as data roots; `rc usecase new/list/show/accept`; `-u`/`RC_USE_CASE`/`defaultUseCase` selection; `refresh --due` across use cases; `.rc-local` ignored at any depth; validators and hooks accept use-case data | `scripts/`, `rc.py`, `.gitignore`, `templates/scope.md`, `templates/usecase.json` | - | Test: two use cases ingest and research in isolation; settings and roles come from the instance; the validator checks each use case |
| WP2 | Research uses the scope: context names `scope.md`; grilling fills "Our needs" from it; a `grill-use-case` skill writes a scope evidence-first; bootstrap creates the first use case | `scripts/research/`, `.agents/skills/` | WP1 | The research test's prompts carry the scope; skills synced |
| WP3 | Docs: ADR 0013, architecture, glossary, README, GUIDE, rc-help, AGENTS triggers | `docs/`, root docs | WP1, WP2 | `rc check` passes |
| WP4 | `foxcale_RC` created on Windows with use case `foxcale`; scope.md written from the session's research with evidence paths; accepted | the new instance | WP1-WP3 | `rc -u foxcale usecase show foxcale` shows an accepted scope; `rc check` passes in the instance |

## Integration and verification

`rc check` in the template and in `foxcale_RC`.

## Failure, rollback and stop conditions

- If sharing config through instance resolution breaks a script's assumptions in a way that is not caught by tests, stop and add the test before continuing.

## Acceptance criteria

- Two use cases in one instance never see each other's sources, profile or research. The tests show this.
- The `foxcale` scope is accepted and research topics under it get it as context.
- `rc check` passes.

## Lifecycle closure

- state: completed
- date: 2026-10-16
- evidence: foxcale_RC instance created with rc-kit new; usecases/foxcale scope written from foxcale.com, di_CC and pv_CC, accepted and set as defaultUseCase; rc check 13 of 13 in the template and in the instance (2026-10-16)
