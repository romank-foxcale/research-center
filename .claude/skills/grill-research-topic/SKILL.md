---
name: grill-research-topic
description: Grill the user, evidence-first, until a research topic becomes an accepted brief - topic, numbered questions, scope, needs, success criteria and source preferences - using the ingested profile so the user is only asked what their material cannot answer, or from scratch when nothing was ingested. Use when the user wants to research something, starts a new topic, or asks for an AI search on a subject.
---

# Grill a research topic

Research is only as good as its brief. Your job is to turn "research X" into questions a pipeline can answer, and needs it can test against. Keep grilling until the brief would survive a sceptical reader, not until you get the first answer.

## 0. Know the user before asking

- If knowledge/profile/index.md exists, read it and the notes relevant to the topic. Skim knowledge/digests/ for the sources that matter.
- If there is no profile, ask once whether the user wants to point the RC at their material first (the rc-ingest skill). If they decline, grill from scratch.
- Never ask what the profile already answers. State it instead ("your API is Python on Nix, so I'll scope to tools that fit that. Right?") and let the user correct it.

## 1. Create the topic

`./rc research new <topic-id> --title "<short title>"` creates research/<topic-id>/brief.md from templates/brief.md.

## 2. Grill, one decision at a time

Use a pick list when the choices are discrete. Recommend an option and say why. Cover:

1. **Why now**: the decision this research feeds, and who will act on it.
2. **Questions**: three to seven, each answerable from evidence. Split vague ones ("is X good?") into measurable ones ("how does X compare to Y on latency and cost at our scale?"). Number them Q1, Q2, ...
3. **Scope and out of scope**: technologies, vendors, the time window (match it to how fast the subject moves: months for news or fast-moving technology, years or decades for settled science, law or history), depth.
4. **Our needs**: the stack, constraints and problems the answer must fit, cited from the profile as `knowledge/profile/<note>.md`. For an individual: what they want to learn or build.
5. **Success criteria**: what the report must enable, such as a choice between options, a go/no-go, or a reading list.
6. **Source preferences**: trusted and distrusted sources, languages, paywalls.
7. **Sources**: `./rc sources list` shows the adapters this RC searches, and `./rc sources packs` the domain packs it could. Recommend enabling a pack that fits the topic (medicine for health questions, software for tools and libraries) with `./rc sources enable <pack>`. When a key source has a feed or a page worth watching, put it in Source preferences so the planner uses the feed or page-watch adapter. When a key source needs an API no adapter covers, `./rc sources new` scaffolds one for the user to finish.
8. **Living**: should the RC keep this topic current? Recommend a cadence from how fast the evidence moves (`weekly` for news-driven topics, `monthly` for active fields, `quarterly` for slow ones, `derived` to follow the plan's horizon, `none` for a one-off question). Agree on `Retire when:`: the decision, date or event after which refreshing stops paying off.

Challenge answers that would make the research unfalsifiable or unbounded. Point out questions the profile shows are already settled.

## 3. Write and accept

- Edit research/<topic-id>/brief.md: replace every `<placeholder>` and keep the section headings.
- Show the user the brief. Change it until they agree.
- `./rc research accept <topic-id>` checks it (every section filled, at least one `- Q1:` line, a valid cadence) and marks it accepted. Then offer to run it with the rc-research skill.

Never start a research run on a brief the user has not accepted.
