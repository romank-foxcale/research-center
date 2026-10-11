---
id: debt.page-watch-whole-page
title: page-watch fingerprints the whole visible page
status: active
summary: The page-watch adapter hashes all of a page's visible text, so a page with rotating banners, dates or cookie notices looks changed on every refresh.
verified_at: 2026-10-11
evidence:
  - scripts/sources/adapters/page_watch.py
relations:
  - docs/debt/index.md
  - docs/decisions/0007-source-adapters.md
---

# page-watch fingerprints the whole visible page

## Statement

A changed fingerprint makes the page a new record for screening on each refresh, which costs a screening call and adds noise to the delta, though the screener's decision and the quote checks keep it from changing conclusions.

## Removal condition

A descriptor filter selecting the part of the page that matters (a CSS selector or a start and end marker), applied before hashing, once a living topic watches a page with volatile content.
