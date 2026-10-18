---
name: rc-share
description: Share Research Center results with people who do not use the repository (a CTO, a CEO, a client) - build a topic's page or the profile's dashboard with ./rc report, confirm with the user, then publish it as a private claude.ai artifact and give the link, updating the same link on later shares. Use when the user wants to share, send, show or present research results, or asks for a link, a page or a dashboard of the research.
---

# Share research

The pages are computed by `./rc report` from the committed outputs, so sharing never changes a conclusion. You publish what the script wrote, as it is.

## Build

- The main screen (every profile's tags and technology cards, a page per card, each profile's research): `./rc home --manifest`. This is what a CTO usually wants.
- One topic: `./rc -p <profile> report <topic> --manifest`.
- The whole profile (a dashboard with every topic's page beside it): `./rc -p <profile> report --manifest`.

Leave out `-p` in an RC without profiles or when `defaultProfile` covers it. The manifest gives:
- `page`, the file to publish;
- `files`, the pages beside it (dashboard only);
- `title`;
- `sharedAt`, the link the page was shared at before, if it was.

Before asking, tell the user in two or three lines what the page says:
- for the main screen: each profile's cards by verdict;
- for a topic: the bottom line, the leading ideas and the certainty.

A topic whose run has not finished shows "Not produced yet" for its missing parts. Say so.

## Confirm

Every publish needs the user's yes, for this page, in this conversation. Ask, naming:
- what is published (one topic, or the dashboard with N topic pages);
- the title;
- whether it updates the existing link or makes a new one.

Pages describe the user's company and products. A published artifact is private to the user until they share the link. Who gets the link is the user's choice; never send it anywhere yourself.

## Publish

- Load the artifact-design skill first, as the Artifact tool requires. The page already meets its contract, so don't restyle it:
  - a short `<title>`;
  - colour tokens with dark mode;
  - phone width without horizontal scroll;
  - no external scripts.
- Publish with the Artifact tool:
  - `file_path` is the manifest's `page`;
  - `files` maps each name in the manifest's `files` to its path;
  - `icon` is `chart` on the first publish;
  - `description` is one sentence: the topic's bottom line, or the profile's topic count.
- If `sharedAt` has a link, pass it as `url` so the link stays the same. Read the artifact first when this conversation has not published it.
- Record the link: `./rc home --shared-at <url>` for the main screen, or `./rc -p <profile> report [<topic>] --shared-at <url>`. Records live in `.rc-local/reports/shares.json`, on this machine only. Another person shares from their own account under their own link.
- Give the user the link. Mention that a refresh or re-run changes the page only when they share again.

## Never

- Never edit the HTML to change wording or a conclusion. Change the brief or a source and re-run, as everywhere in the RC.
- Never publish a page the script did not write, or one from another profile than the user asked for.
- Never publish to an artifact someone else owns unless the user has edit access.
