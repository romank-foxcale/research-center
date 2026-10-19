---
id: hacks.windows-replace-retry
title: Atomic JSON writes retry the rename on Windows
status: active
summary: rc.write_json renames a .tmp file onto its target; on Windows that fails with Access is denied while any process, even an antivirus scan or the indexer, holds the target open, so the rename is retried for about four seconds.
verified_at: 2026-10-18
evidence:
  - scripts/runner/rc.py
  - scripts/sources/sources.py
relations:
  - docs/decisions/0012-windows-native-uv.md
  - docs/hacks/index.md
---

# Atomic JSON writes retry the rename on Windows

## Statement

`rc.write_json` writes `<file>.tmp` and then renames it onto `<file>`, so no reader ever sees half a file. On Windows that rename fails with `PermissionError: [WinError 5] Access is denied` if any other process has the target open at that moment. Sharing delete does not prevent it. Real-time antivirus scanning and the search indexer open files right after a write. The research pipeline and its test rewrite the same JSON files within milliseconds, so they hit this window now and then.

This explains a `research_test.py` failure that happened once and never again. It occurred during `rc check` right after `rc upgrade`, when the scanner was busy with fresh files. Under a simulated scanner that briefly opens each new file and shares read, write and delete, the test failed in 7 of 14 runs. With the retry it passed 12 of 12. In 230 runs without a scanner, it never failed, including runs with random delays and 16 copies at once.

`rc.replace` retries a refused rename after 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1 and 2 seconds before it lets the error through. On other systems it does not retry, because a refused rename there is a real permission problem. `sources.log_search` writes through `rc.write_json` for the same reason.

## Removal condition

Remove it when Python renames with POSIX semantics on Windows (`FILE_RENAME_FLAG_POSIX_SEMANTICS`, which replaces a file that is open with shared delete), or when the RC stops supporting native Windows (docs/decisions/0012-windows-native-uv.md).
