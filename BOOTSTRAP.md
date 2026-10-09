# Research Center bootstrap

This file is the first instruction for a model started from the target RC folder.

## Determine the roots

- `template_root` is the folder containing this file; usually `<target_root>/rc_template`.
- `target_root` is the parent of `rc_template`; it becomes the RC.
- Do not change, move or commit `template_root` into the target RC. It is a read-only seed.

Immediately read `<template_root>/.agents/skills/grill-rc-bootstrap/SKILL.md` in full. AI tools do not discover skills inside a child Git repository automatically.

## Determine the mode

If the current folder already has a `research-center.json` with status `discovery` and nothing besides the template files, the RC was already materialized by `rc-kit new`. In that case `template_root` equals `target_root`: do not run the installer, and continue grilling from step 3 of the "New RC" section of the `grill-rc-bootstrap` skill.

- `new`: `target_root` has no RC files apart from `rc_template`. Run from `target_root`:

  ```bash
  ./rc_template/rc bootstrap install .
  ```

- `migration`: `target_root` already holds research material in another format: notes, reading lists, a knowledge base, earlier reports. Do not run the installer into it. First do a read-only inventory and a mapping, then materialize an RC next to it and bring the material in as sources (`./rc ingest add folder ...`), never by copying it into `knowledge/` or `research/` by hand.

If the mode is unclear, do not write to the target folder until it is clarified.

## Fixed topology

```text
Projects/
├── project1_CC/
├── project1_RC/        ← the Research Center, its own private repo
├── repos/              ← shared base clones (CCs); an RC may ingest them as git sources
└── worktrees/
```

Relative to any `<project>_RC`:

- what the RC knows: `sources/`, `knowledge/digests/`, `knowledge/profile/`;
- what it researched: `research/<topic>/`;
- local run state: `.rc-local/` (ignored);
- the RC never writes into a CC, a repo or a worktree: ideas leave as `research/<topic>/handoff.md`.

This topology can only be changed by a separate, explicit decision of the user.

In normal work use the executable interface:

```bash
./rc ingest add <folder|git|url|notion|gdrive> <locator...> --note "..."
./rc ingest run
./rc research new <topic> --title "..."
./rc research accept <topic>
./rc research run <topic>
./rc watch
```

## Acceptance criteria

Do not declare the bootstrap finished until:

1. `research-center.json` reflects the agreed budgets and limits, and its status is `ready`.
2. The remote is private (verified with `gh`, or `privateRemoteConfirmed` set by the user for a non-GitHub remote), or the RC deliberately has no remote yet.
3. Every pipeline role uses a provider the user is logged in to (`./rc doctor`, `./rc settings`).
4. `./rc agents check` and `./rc check` pass, or the unverified environment is explicitly recorded.
5. The target RC does not depend on the contents of `rc_template/`.

After that, tell the user that `rc_template/` can be deleted. Do not delete it yourself.
