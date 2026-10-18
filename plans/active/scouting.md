# scouting: Profiles with interest tags, a scouting loop that turns new releases into technology cards, and a shared trends feed

Lifecycle: active
Planning status: accepted

## Outcome

The RC works as a technology scout, the job foxcale pays consultants for today. Unlike them, it says plainly when something does not fit.

1. **Profiles.** A profile has:
   - a name and a description;
   - a type: `company` or `personal`;
   - editable interest tags.

   The type sets the licence rule:
   - **company:** only permissive licences are usable (MIT, Apache-2.0, BSD, ISC, MPL-2.0). Copyleft, non-commercial, source-available and unknown licences are flagged on every card, never hidden.
   - **personal:** any licence is usable.
2. **Interest tags.** The user writes tags directly, or drops material into the profile's `inbox/`. The profile agent then proposes tags, each with a reason and the source it came from, and the user accepts, edits or removes them. Example tags for foxcale: digital forensics, e-discovery, Japanese OCR, technology-assisted review, endpoint telemetry.
3. **Scouting.** A run has four steps:
   1. **Discover**, with no agent: trending and new GitHub repositories, recent arXiv and OpenAlex papers, and news, searched per tag. Anything seen before is skipped.
   2. **Triage**, one agent call: rank the finds against the profile's tags, products and constraints, and keep the few worth a card.
   3. **Evaluate**, one call per pick: write a **technology card**.
   4. **Challenge**, one call: a sceptic tests every card's fit claims against the profile and the stored pages.
4. **The technology card** has two layers:
   - **For leaders:** what it is in two lines, what it could do for us, where it would plug in, the verdict (worth testing, watch, or not a fit) and why.
   - **For engineers:**
     - how it works;
     - the exact component it would touch or replace, and what that component does today;
     - licence against the profile's type, maturity and activity;
     - alternatives already in use;
     - pros, cons and risks;
     - an evaluation plan: the experiment, the metric, the pass bar and the effort.

   "Not a fit, because…" is a full result. A claim like "JEV can replace FLAR" comes back with the component, what each actually does, and what would have to change.
5. **Global trends.** A shared feed scouts change that is not tied to any profile but may affect several, for example a better agent harness or a new model class. Each trend card names the profiles and components it may affect.
6. **The main screen.** One page holds the global trends, then each profile's tags and latest cards. It is shared with the rc-share skill like any page.
7. **Deep dive.** Any card can be escalated into the existing question-driven study, as was done for FLAR. The brief is pre-filled from the card.

Scouting runs weekly (`rc scout --due`, scheduled) and on demand (`rc scout`).

## Non-goals

- Replacing the deep-dive pipeline. It stays, behind cards.
- A hosted app or a login. Pages stay computed files, shared as artifacts.
- Writing into product repositories or Control Centers. A card's evaluation plan leaves as a handoff the user takes to a CC.

## Evidence and current behavior

- The user's statement of intent, on 2026-10-18:
  - profiles with a type;
  - tags written by hand or drawn from a drop folder;
  - scouting by tags into cards that serve both non-engineers and engineers;
  - a shared trends screen.

  The motivating example: consultants proposed replacing FLAR with JEV, and the evaluation showed it would not work.
- What exists to build on:
  - use cases with isolated data (ADR 0013);
  - ingest and the cited profile;
  - source adapters for GitHub, arXiv feeds, OpenAlex, Crossref and news (ADR 0007);
  - screening and quote checks;
  - the sceptic and judge roles;
  - report pages and sharing (ADR 0014).
- What does not fit the intent:
  - every topic needs a hand-grilled brief;
  - one run took 36 minutes and 20 agent calls (flar-core-loop, 2026-10-18);
  - a profile's interests sit in a long `scope.md` and are not editable tags;
  - nothing scouts without a question, and nothing is shared across profiles.

## Affected scope

| Repository | Worktree | Read/write | Interfaces |
| --- | --- | --- | --- |
| research-center | local clone | write | `rc profile`, `rc tags`, `rc scout`, `rc report`, `scripts/`, skills, templates, docs |
| foxcale_RC | `%USERPROFILE%\Projects\foxcale_RC` | upgrade | `usecases/foxcale/` becomes `profiles/foxcale/`, and the first real scout runs there |

## Invariants and decisions

- **Rename, decided by the user on 2026-10-18.** "Use case" becomes "profile" everywhere:
  - `profiles/<id>/` with `profile.json` (name, description, type, tags);
  - `rc profile new|list|show|edit`, and `-p <id>` (`-u` is kept as an alias for one release);
  - `rc upgrade` moves `usecases/` to `profiles/`.

  `scope.md` becomes an optional longer context document, and research no longer requires it.
- **Licences, decided by the user.** For a company profile, permissive licences pass. Everything else is flagged on the card with its reason.

  The runner, not an agent, reads the licence (the GitHub licence field or a stated SPDX id) and classifies it from `templates/licences.json`. An unreadable licence is `unknown`, and unknown is flagged.
- **Cadence, decided by the user:** weekly plus on demand. A scout run of one profile is budgeted at about 10 agent calls (`budget.scoutCalls`).
- **Deep dive kept, decided by the user.** `rc scout dive <card>` creates a brief from the card for the existing pipeline.
- **The runner fetches, agents read.** Discovery is adapter code. The runner stores every README, paper or page a card relies on. Card claims about the find quote a stored page, checked like research claims. Claims about the user come from the profile notes.
- **Seen and dismissed.** Each profile keeps a seen-list, so a find gets one card, not one per run. A dismissed card is never re-raised unless the find changes materially (a new major release).

## Open questions

| Question | Impact | Owner/next evidence |
| --- | --- | --- |
| Which sources does "trending" use for GitHub? | Search sorted by stars since a date is supported; github.com/trending has no API | Decide in WP3 from what the API returns |
| Should tags be editable in the shared page itself? | It would need the artifact database capability; the repository would stay the source of truth | Decide after WP6 |

## Work packages

| ID | Outcome | Write scope | Depends on | Completion check |
| --- | --- | --- | --- | --- |
| WP1 | Profiles: rename use cases (folders, commands, `-p`, validators, hooks, skills, docs); `profile.json` with name, description, type; `templates/licences.json` and a licence classifier; `rc upgrade` migrates `usecases/` | `rc.py`, `scripts/`, `templates/`, `.agents/skills/`, docs | - | Use-case tests pass as profile tests; the upgrade moves a fixture instance; the licence classifier is tested |
| WP2 | Tags: `rc tags list|add|remove|rename`; the `inbox/` folder is auto-registered as a source; the profile agent proposes tags with reasons and sources; `rc tags suggest|accept` | `scripts/`, profile skill | WP1 | A test proposes, accepts, edits and removes tags; inbox files are ingested |
| WP3 | Discovery: adapters gain a recent mode (GitHub created or pushed since a date and sorted by stars, arXiv and OpenAlex recent, news); `rc scout discover` writes candidates per tag, deduplicated against the seen-list; no agent | `scripts/sources/`, `scripts/scout/` | WP2 | Fixture adapters return candidates; seen finds are skipped |
| WP4 | Triage, cards and challenge: triage, evaluator and sceptic roles; the card contract (leader and engineer parts, verdict, component, evaluation plan); the runner fetches and stores evidence, checks quotes and stamps the licence verdict; cards as JSON and Markdown; `rc scout` end to end within budget | `scripts/scout/`, `.agents/skills/`, `templates/agents/` | WP3 | A fixture run produces cards, including a "not a fit" card for a JEV-like find that claims to replace a profile component; a GPL repository on a company profile is flagged |
| WP5 | Global trends: instance-level `trends/` with its own tags; trend cards name the profiles and components they may affect | `scripts/scout/` | WP4 | A fixture trend card names an affected profile |
| WP6 | Main screen: `rc report` writes the main page (trends, then profiles with tags and latest cards) and card pages; rc-share publishes it | `scripts/report/`, rc-share | WP4, WP5 | The report test covers the main page and card pages |
| WP7 | Deep dive and schedule: `rc scout dive <card>` drafts a brief; `rc scout --due` runs weekly profiles and trends; GUIDE has the Task Scheduler line | `scripts/scout/`, GUIDE | WP4 | A test turns a card into a brief; `--due` skips profiles that are not due |
| WP8 | Docs (ADR 0015, README, GUIDE, rc-help), the foxcale_RC upgrade with foxcale's tags, and the first real scout run shown to the user | docs, foxcale_RC | WP1-WP7 | `rc check` passes in both; the user has reviewed the first real cards |

## Integration and verification

- `rc check` in the template, with a new scout test.
- In foxcale_RC: the first real `rc scout`, reviewed with the user, and its main page shared.

## Failure, rollback and stop conditions

- If GitHub's unauthenticated rate limit blocks discovery, use the user's `gh` login token through `gh api`, never a token stored in the repository. If neither works, report it.
- Stop and ask if a scout run exceeds its budget twice in a row: the triage cut-off is then wrong.

## Acceptance criteria

- The user can create a personal profile and a company profile, edit tags, run `rc scout`, and read cards that a non-engineer understands and an engineer can act on.
- A find that does not fit is reported as "not a fit", with the component and the reason.
- A licence the profile cannot use is flagged on its card.
- One scout run of one profile stays within about 10 agent calls.

## Lifecycle closure

Not closed.
