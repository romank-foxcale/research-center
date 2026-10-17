# report-ui: Research results as shareable pages: a topic report, a use-case dashboard, sharing from Claude Code, explainer briefs

Lifecycle: active
Planning status: accepted

## Outcome

Leadership (a CTO or CEO) can read a research topic without opening the repository:

- `rc report <topic>` writes one self-contained HTML page for a topic. It works offline, needs no server, has no external scripts, and suits light and dark mode. It has two layers:
  - **The first screen** is for decisions:
    - the question and the bottom line (the report's TL;DR);
    - the ideas ranked by ring, with the judge's verdict, effort, what each would replace, risks and next step;
    - each question's certainty, with the reasons it was downgraded.
  - **Below it** is the evidence:
    - the screening funnel and its exclusion reasons;
    - the claim verdicts and source reliability;
    - each question's hypothesis matrix as a heatmap, with hypotheses ranked by inconsistent evidence;
    - the assumptions;
    - the full report, with every `[C#]` linked to its claim;
    - a claims appendix (verdict, credibility, quote, source link);
    - the history of a living topic.
- `rc report` without a topic writes a dashboard for the use case: every topic with its status, verdicts and last change, linking to the topic pages.
- From Claude Code, "share the <topic> research" runs `rc report` and publishes the page as a private claude.ai artifact. Updating it keeps the same link. Each publish needs the user's OK.
- `rc explainer <topic>` writes an explainer brief (the idea, how it works, where it plugs in, its cited claims). The user can take it to a video tool such as thetaupdate's `/new-edu` workflow.

## Non-goals

- A hosted web app, a server or a login. Pages are files; sharing goes through artifacts or the file itself.
- Editing research from the page. The page is derived output, and conclusions change only by re-running.
- Rendering videos inside the RC. thetaupdate stays a separate private repository (`romank-foxcale/thetaupdate`), and the RC never writes into it.

## Evidence and current behavior

- A finished topic holds structured outputs: brief.md, source-plan.json, screening.json (flow, criteria, records), claims.json (sources, claims), ideas.json (ideas, questions with assumptions and ACH matrices), judgement.json (claims, ideas, assumptions, answers with certainty), fit.json (rings, effort, next step, history), watch.json (log) and report.md (`scripts/research/research.py` OUTPUTS).
- Today the only reading surface is the Markdown in the repository. The four-day-week run (2026-10-11, 161 claims, 54 sources) produced a 4-question report that reads well in an editor, but it cannot be shared with someone without repository access.
- The user wants to share results with summaries with a CTO and CEO, through Claude Code, and to see the research visually (session, 2026-10-16).
- thetaupdate (`C:\Users\KozyrevRoman\Desktop\Code\thetaupdate`) renders 1080x1920 explainer videos with matplotlib, under its own sourcing rules. It suits a short "how this works" clip, not an interactive report.

## Affected scope

| Repository | Worktree | Read/write | Interfaces |
| --- | --- | --- | --- |
| research-center | local clone | write | `rc report`, `rc explainer`, `scripts/report/`, a sharing skill, docs |
| foxcale_RC | `%USERPROFILE%\Projects\foxcale_RC` | upgrade only | `rc upgrade` brings the commands in |

## Invariants and decisions

- **The page is computed, never written by an agent.** `scripts/report/report.py` renders the topic's committed outputs deterministically. It makes no model call, so a report page costs no budget and can be rebuilt at any time.
- **Pages are derived and not committed.** They are written to `<data root>/.rc-local/reports/` (ignored) through `rc.write_text`, so secrets are redacted on the way out like every other runner write.
- **No injection.** Markdown is rendered by markdown-it-py with raw HTML off, and every other value is HTML-escaped. Links are allowed only for http and https. Text from the web stays text.
- **Self-contained.** Inline CSS and SVG only, with no CDN, so the page works offline, as an attachment and as an artifact. A small inline script adds filtering; the page reads fully without it.
- **Sharing is the user's act.** The skill publishes only after the user confirms for that topic. Pages describe client products, so the default is a private artifact; the user decides who gets the link.

## Open questions

| Question | Impact | Owner/next evidence |
| --- | --- | --- |
| Is WP4 (explainer briefs) worth building? | Deferred on 2026-10-17 until a real use-case topic exists to test it on | The user, after the first foxcale topic |
| Is a Japanese summary layer needed for leadership? | Pages are English, per the repository rule; a translated summary would be a second derived page | Ask once the first foxcale topic is shared |

## Work packages

| ID | Outcome | Write scope | Depends on | Completion check |
| --- | --- | --- | --- | --- |
| WP1 | `rc report <topic>`: the topic page described above, built from the topic's outputs; it tolerates topics run before a stage existed (no matrix, no fit) | `scripts/report/`, `rc.py`, `pyproject.toml` | - | Report test: a fixture topic renders every section; injected HTML stays escaped; a secret in the input is redacted; a partial topic renders; the four-day-week topic renders |
| WP2 | `rc report` with no topic: a use-case dashboard linking topic pages, with the scope's title and each topic's status, ring counts and last change | `scripts/report/` | WP1 | The report test renders a dashboard across two topics |
| WP3 | A `rc-share` skill: build the page, confirm with the user, publish or update a private artifact, give the link; AGENTS trigger; rc-help | `.agents/skills/`, AGENTS.md | WP1, WP2 | Skills synced; a share of the four-day-week page done with the user |
| WP4 | `rc explainer <topic> [--idea I#]`: a Markdown explainer brief (what it is, how it works, where it plugs in, value in the scope's measures, cited claims with source links) for a video or slide tool | `scripts/report/` | WP1 | The report test checks an explainer's sections and citations |
| WP5 | Docs: ADR 0014, architecture, README, GUIDE; foxcale_RC upgraded | `docs/`, root docs | WP1-WP4 | `rc check` passes in the template and in foxcale_RC |

## Integration and verification

`rc check` (a new "report test" entry), and a manual look at the four-day-week page in a browser at phone and desktop width, in light and dark mode.

## Failure, rollback and stop conditions

- If a topic's outputs cannot be rendered without guessing at a missing field, show the section as absent and say so on the page. Never invent content.

## Acceptance criteria

- A CTO can read a topic's page without the repository and answer: what we should do, how sure we are, and why. Each statement on the page traces to a claim and a source.
- Re-running `rc report` on unchanged outputs gives the same bytes.

## Lifecycle closure

Not closed.
