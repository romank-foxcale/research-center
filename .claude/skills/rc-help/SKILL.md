---
name: rc-help
description: Explain what the Research Center can do - its pipeline, its skills grouped by purpose and the ./rc commands behind them - and help the user pick where to start. Use when the user asks for help, what the RC can do, which skills exist, or how ingest, grilling or research work.
---

# Research Center help

Explain the RC in this order, briefly, then offer a pick list of where to start.

## Two loops

```
scout:      profile (type, tags) → discover → triage → technology cards → sceptic → main screen
deep dive:  grill → plan → search → screen → collect → analyze → critique → judge → apply → report → share
```

1. **Profile** (grill-profile, `./rc profile new|edit`, `./rc tags`): the RC works for a profile, such as a company, a product line or a person.
   - Each profile has its own type, interest tags, sources and topics.
   - A company profile may use only permissive licences; a personal one may use any.
   - Tags are written by the user, or proposed from ingested material and the profile's `inbox/` (`./rc tags suggest`).
   - An optional `scope.md` holds the longer context.
2. **Ingest** (rc-ingest, `./rc ingest`): point at folders, repos, URLs, Notion and Drive. Their text is committed with secrets redacted, then digested into cited profile notes. Both loops read them.
3. **Scout** (rc-scout, `./rc scout`, about 12 agent calls, weekly with `./rc scout --due`):
   - discovery finds what is new for every tag on GitHub, arXiv and OpenAlex, with no agent calls;
   - triage picks the few finds worth a card;
   - each card says what the find is, where it plugs in, and a verdict (worth testing, watch, not a fit) with why, for leaders and for engineers, quoting the stored README or paper;
   - a sceptic checks every card.

   `./rc trends` does the same for a shared feed and names the profiles each trend affects. `./rc home` is the main screen.
4. **Deep dive** (`./rc scout dive <card>`, or grill-research-topic, then rc-research): a full cited study.
   - A source plan with competing hypotheses; screened searches.
   - Two researchers (Claude Opus and Sonnet) read the included records and search the web; quotes are checked against stored pages.
   - An analysis, then two sceptics; an anonymous judge settles them.
   - Fit to the user's repos, then a report that opens in plain words.

   A topic with a cadence stays living (`./rc research refresh`).
5. **Handoff**: ideas worth acting on become a Control Center task plan (`research/<topic>/handoff.md`), or a card's evaluation plan goes to the Control Center. Code changes happen in a CC, never in the RC.
6. **Share** (rc-share): the main screen (`./rc home`), a topic's page or a profile's research dashboard, as a private claude.ai link.

## User-facing skills

| Skill | Use it to |
| --- | --- |
| grill-rc-bootstrap | create and set up an instance (private remote, logins, models, budgets) |
| grill-profile | create a profile, set its type and description, manage its interest tags, write its scope |
| rc-ingest | add and ingest sources, read the profile |
| grill-research-topic | turn a topic into an accepted brief |
| rc-research | run, follow and present research |
| rc-scout | scout for a profile: new repositories and papers per tag, triaged into technology cards with a verdict |
| rc-share | share a topic or the profile's dashboard as a link |
| rc-help | this overview |

The ingest-*, research-*, scout-* and profile-tags skills are role instructions the runners load for agents. They are not for direct use.

## Commands

Outside an RC, the `rc-kit` command works like the Control Center's `cc-kit`: `rc-kit new <name>` creates `~/Projects/<name>_RC`, and `rc-kit list`, `rc-kit open <name> <tool>`, `rc-kit doctor` and `rc-kit update` do what their names say. GUIDE.md covers installing it.

Inside an RC, `./rc help` lists every command. Most used: `./rc doctor`, `./rc profile list|new|edit`, `./rc tags list|add|suggest|accept`, `./rc scout`, `./rc scout cards|dismiss`, `./rc trends`, `./rc home`, `./rc ingest add|run|list`, `./rc research new|accept|run|show|refresh`, `./rc report`, `./rc sources list|search|packs|enable|new|test`, `./rc watch`, `./rc roles`, `./rc validate`, `./rc check`.

## Where things live

- sources/<id>/: committed text
- knowledge/digests/: one digest per source
- knowledge/profile/: the cited profile
- research/<topic>/: brief, ledger, analysis, critique, judgement, fit, report, handoff
- docs/: the RC's own decisions and rules

In an instance with profiles, these folders live under `profiles/<id>/`, and commands take `-p <id>`.

Finish by asking which to start with: bootstrap, a profile and its tags, a scout, ingest, a research topic, or sharing results.
