---
name: grill-rc-bootstrap
description: Create a new Research Center instance from the research-center template and set it up - private remote, provider logins, role models, budgets - then hand over to ingest and grilling. Use when the user asks to create, set up, bootstrap or configure a Research Center, or starts in the template clone.
---

# Bootstrap a Research Center

The template (research-center) is public and holds no data. An instance is the user's own **private** repo, made from it. Keep grilling until every step below is verified, not just answered.

## 1. Make the instance

- Ask where it lives, for example `../<name>_RC` next to the template clone.
- From the template root: `./rc bootstrap install <dir>`. It copies the tracked files, writes research-center.json, copies the default roles to catalog/agents and runs `git init`.
- Tell the user to continue the session from the instance root. A session in the template has no research-center.json and refuses to ingest.

## 2. Private remote

- The instance commits source text from company repos, Notion and Drive. Its remote must be private.
- The user creates the repo, or you run `gh repo create <owner>/<name> --private` after they confirm the owner and name. Then `git remote add origin <url>`.
- A non-GitHub remote can't be checked. The user confirms it is private, and only then do you set `"privateRemoteConfirmed": true` in research-center.json.

## 3. Logins and models

- `./rc doctor` shows Nix, gh and the provider logins (claude, codex, cursor-agent). The roles use the user's own subscriptions, and the RC stores no credentials.
- `./rc roles` lists each role, its provider, model and pipeline slot. Ask which subscriptions the user has. Move roles off a provider they lack, for example `./rc roles set judge --provider claude --model opus`. Researchers need web access (claude or codex). The connector reader needs claude. Cursor roles are read-only.
- Notion and Drive ingest need the claude.ai connectors to be connected for the user's Claude account. `claude mcp list` shows them.

## 4. Budgets and limits

Agree on `budget.ingestCalls` and `budget.researchCalls` (agent calls per run), `ingest.maxSourceBytes`, and `research.maxSourcesPerResearcher` in research-center.json. A run that hits a budget stops and can resume.

## 5. Verify and hand over

- `./rc agents sync`, then `./rc check`. Every check must pass.
- Commit the instance only with the user's go-ahead.
- Then ask: does the user want to point the RC at their material first (rc-ingest), or grill a topic from scratch (grill-research-topic)?
