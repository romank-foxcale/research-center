---
id: debt.flake-check-copies-instance
title: ./rc check copies the whole instance, sources included, into the Nix store
status: superseded
summary: Flake checks evaluate the repository as a path, so an instance with large committed sources is copied into the store on every ./rc check; ingest and research avoid it by building nix/tools.nix alone.
verified_at: 2026-10-16
evidence:
  - rc.py
relations:
  - docs/decisions/0012-windows-native-uv.md
  - docs/debt/index.md
  - docs/architecture/research-center.md
---

> Superseded by [docs/decisions/0012-windows-native-uv.md](../decisions/0012-windows-native-uv.md): Nix is gone, and `rc check` reads the working tree directly.

# ./rc check copies the whole instance, sources included, into the Nix store

## Statement

`nix flake check` copies every tracked file. For an instance with hundreds of megabytes of source text, each check costs time and store space. `./rc validate` runs the same validators without Nix.

## Removal condition

Split the instance data from the flake: for example, the data checks become an app that reads the working tree. Or Nix gains lazy path copying for flakes.
