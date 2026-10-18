---
name: rc-scout
description: Run and present scouting for a profile with ./rc scout - discovery of new repositories and papers for its interest tags, triage, technology cards with a plain verdict (worth testing, watch, not a fit) and a sceptic check - then walk the user through the cards. Use when the user wants to scout, asks what is new for a profile or a tag, asks whether a technology fits them, or wants the cards explained, dismissed or deepened.
---

# Scout for a profile

## Run

1. `./rc profile list`, then work in one profile with `-p <id>`. It needs interest tags (`./rc -p <id> tags list`). Without tags, use the grill-profile skill first.
2. Run `./rc -p <id> scout` in the background and follow it with `./rc -p <id> watch`. Relay each step as it happens:
   - discovery, which finds new items per tag with no agent call;
   - triage, which picks the few worth a card;
   - one card per pick;
   - the sceptic's review.

   Report failed sources and rejected replies too. A run costs about `scout.calls` agent calls (12 by default).
3. `./rc -p <id> scout discover` alone costs no agent calls. `./rc -p <id> scout run --no-discover` triages what is already open.
4. A provider that is logged out stops the run. Tell the user which login to fix (`./rc doctor`). Never switch to another model.

## Present

Read the new cards (`profiles/<id>/scout/cards/<card>.md`), then give the user:

- each card in one or two lines, grouped by verdict: worth testing, then watch, then not a fit. Give the reason, the component and the licence line where it limits shipping;
- where the sceptic changed or questioned a verdict, and why;
- for "worth testing": the evaluation plan (experiment, metric, pass bar, effort). That is what an engineer would take to the profile's Control Center;
- how many candidates triage passed, so the user knows what was not carded.

Lead with plain words. Engineers' detail is in the card when the user asks.

## After

- **Dismiss** a card the user does not want raised again: `./rc -p <id> scout dismiss <card>`.
- **Deep dive:** when a card needs a real study, offer a research topic from it. Use grill-research-topic with the card's component, claims and evaluation plan as the starting brief.
- **See and share:** `./rc home` writes the main screen with a page per card (`.rc-local/reports/home/index.html`). Use rc-share for a link a CTO can read.
- **Commit** `profiles/<id>/scout/` when the user asks.

## Never

- Never edit a card to change a verdict. Change the tags or the profile and run again; the sceptic and the evaluator decide.
- Never present a card's licence as usable when the card says it is not.
