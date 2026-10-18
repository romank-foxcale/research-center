---
name: rc-help
description: Explain what the Research Center can do - its pipeline, its skills grouped by purpose and the ./rc commands behind them - and help the user pick where to start. Use when the user asks for help, what the RC can do, which skills exist, or how ingest, grilling or research work.
---

# Research Center help

Explain the RC in this order, briefly, then offer a pick list of where to start.

## The pipeline

```
profile (type, tags) → ingest (optional, repeatable) → grill → plan → search → screen → collect → analyze → critique → judge → apply → report → share
```

0. **Profile** (grill-profile, `./rc profile new|edit`): the RC works for a profile (a company, a product line, a person) with its own type, interest tags, sources and topics. A company profile may use only permissive licences, a personal one any. An optional scope.md says whom the research serves, their products and plug-in points, hard constraints and how value is measured.

1. **Ingest** (rc-ingest, `./rc ingest`): point at folders, repos, URLs, Notion, Drive. Their text is committed, with secrets redacted, then digested and reduced into a cited profile.
2. **Grill** (grill-research-topic, `./rc research new|accept`): turn a topic into an accepted brief. The profile answers whatever it can, so the user is only asked the rest.
3. **Research** (rc-research, `./rc research run`): a source plan with competing hypotheses; the adapters search and a screener includes or excludes each record; two researchers (Claude Opus and Sonnet) read them and search the web, and every cited page is stored with its quotes checked; an analysis; two sceptics (Claude Opus and Sonnet) try to disprove each claim; an anonymous judge settles them; the surviving ideas are fitted to the user's repos; a cited report comes out. A topic with a cadence stays living: `./rc research refresh` re-searches it.
4. **Handoff**: ideas ranked ADOPT or TRIAL become a Control Center task plan (research/<topic>/handoff.md). Code changes happen in a CC, never in the RC.
5. **Share** (rc-share, `./rc report`): a topic's page or the profile's dashboard, as self-contained HTML, published as a private claude.ai link for people without the repository.

## User-facing skills

| Skill | Use it to |
| --- | --- |
| grill-rc-bootstrap | create and set up an instance (private remote, logins, models, budgets) |
| grill-profile | create a profile, set its type and description, manage its interest tags, write its scope |
| rc-ingest | add and ingest sources, read the profile |
| grill-research-topic | turn a topic into an accepted brief |
| rc-research | run, follow and present research |
| rc-share | share a topic or the profile's dashboard as a link |
| rc-help | this overview |

The ingest-*, research-* skills are role instructions the runners load for agents. They are not for direct use.

## Commands

Outside an RC, the `rc-kit` command works like the Control Center's `cc-kit`: `rc-kit new <name>` creates `~/Projects/<name>_RC`, and `rc-kit list`, `rc-kit open <name> <tool>`, `rc-kit doctor` and `rc-kit update` do what their names say. GUIDE.md covers installing it.

Inside an RC, `./rc help` lists every command. Most used: `./rc doctor`, `./rc profile list|new|edit`, `./rc tags list|add|suggest|accept`, `./rc ingest add|run|list`, `./rc research new|accept|run|show|refresh`, `./rc report`, `./rc sources list|search|packs|enable|new|test`, `./rc watch`, `./rc roles`, `./rc validate`, `./rc check`.

## Where things live

- sources/<id>/: committed text
- knowledge/digests/: one digest per source
- knowledge/profile/: the cited profile
- research/<topic>/: brief, ledger, analysis, critique, judgement, fit, report, handoff
- docs/: the RC's own decisions and rules

In an instance with profiles, these folders live under `profiles/<id>/`, and commands take `-p <id>`.

Finish by asking which to start with: bootstrap, a profile, ingest, a research topic, or sharing results.
