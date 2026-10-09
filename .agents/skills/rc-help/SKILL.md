---
name: rc-help
description: Explain what the Research Center can do - its pipeline, its skills grouped by purpose and the ./rc commands behind them - and help the user pick where to start. Use when the user asks for help, what the RC can do, which skills exist, or how ingest, grilling or research work.
---

# Research Center help

Explain the RC in this order, briefly, then offer a pick list of where to start.

## The pipeline

```
ingest (optional, repeatable) → grill → plan → collect → analyze → critique → judge → apply → report
```

1. **Ingest** (rc-ingest, `./rc ingest`): point at folders, repos, URLs, Notion, Drive. Their text is committed, with secrets redacted, then digested and reduced into a cited profile.
2. **Grill** (grill-research-topic, `./rc research new|accept`): turn a topic into an accepted brief. The profile answers whatever it can, so the user is only asked the rest.
3. **Research** (rc-research, `./rc research run`): a source plan; Claude and GPT search the web in parallel and every cited page is stored with its quotes checked; an analysis; sceptics (Claude, GPT, Grok) try to disprove each claim; an anonymous judge settles them; the surviving ideas are fitted to the user's repos; a cited report comes out.
4. **Handoff**: ideas ranked ADOPT or TRIAL become a Control Center task plan (research/<topic>/handoff.md). Code changes happen in a CC, never in the RC.

## User-facing skills

| Skill | Use it to |
| --- | --- |
| grill-rc-bootstrap | create and set up an instance (private remote, logins, models, budgets) |
| rc-ingest | add and ingest sources, read the profile |
| grill-research-topic | turn a topic into an accepted brief |
| rc-research | run, follow and present research |
| rc-help | this overview |

The ingest-*, research-* skills are role instructions the runners load for agents. They are not for direct use.

## Commands

Outside an RC, the `rc-kit` command works like the Control Center's `cc-kit`: `rc-kit new <name>` creates `~/Projects/<name>_RC`, and `rc-kit list`, `rc-kit open <name> <tool>`, `rc-kit doctor` and `rc-kit update` do what their names say. GUIDE.md covers installing it.

Inside an RC, `./rc help` lists every command. Most used: `./rc doctor`, `./rc ingest add|run|list`, `./rc research new|accept|run|show`, `./rc watch`, `./rc roles`, `./rc validate`, `./rc check`.

## Where things live

- sources/<id>/: committed text
- knowledge/digests/: one digest per source
- knowledge/profile/: the cited profile
- research/<topic>/: brief, ledger, analysis, critique, judgement, fit, report, handoff
- docs/: the RC's own decisions and rules

Finish by asking which to start with: bootstrap, ingest, or a research topic.
