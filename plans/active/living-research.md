# living-research: a domain-agnostic research engine with structured sources, living topics and graded evidence

Lifecycle: active
Planning status: accepted

## Outcome

The RC researches any subject, not only software or AI, and keeps every topic current instead of producing one report and stopping:

1. **Structured sources.** Collection no longer depends on web search alone. The runner queries a registry of **source adapters**: general ones that work for any topic and domain packs enabled per topic. It screens what they return and follows citations. Web search stays as one avenue among many.
2. **Living topics.** An accepted topic carries saved searches and a cadence. `./rc research refresh <topic>` re-runs them, screens only what is new, re-checks claims that have gone stale, re-judges only what changed, and writes a **delta**: what is new, which verdicts flipped, which answers and fit rings moved. A topic is `living`, `paused` or `retired`.
3. **Graded evidence.** Every source carries an evidence type and a reliability grade, and every claim a credibility grade. Every answer gets a certainty level with the reasons it was downgraded. The report states its confidence in calibrated words.
4. **Transparent search.** Every query, its adapter, date and result count is recorded. Every candidate is logged as identified, duplicate, screened, excluded (with a reason) or included, so a reader can see what was looked at and why it was dropped.

The method is taken from established practice (see "Adopted practices"), and every point is turned into a runner mechanism or a role contract, never a guideline nobody checks.

## Non-goals

- No hosted service, daemon or server. Refresh is a command. The user schedules it with cron, a systemd timer, Windows Task Scheduler or a Claude scheduled task.
- No new agent tools. Adapters run inside the runner. Roles stay read-only exactly as in `docs/decisions/0003-read-only-agents.md`.
- No stored credentials. v1 adapters are keyless. Adapters that need a key read it from an environment variable only, and the key is never written to the repo.
- No full systematic-review tooling: no dual human screening, no meta-analysis statistics, no risk-of-bias forms per study type.
- No cross-RC sharing. The claim store stays inside one instance.
- The hardening findings from the 2026-10-10 review are out of scope, except those this plan builds on (WP0).

## Evidence and current behavior

- Collection is web search by the researcher roles only. `templates/agents/researcher-*.json` use `web-read` access, `scripts/runner/providers.py:30` grants `WebSearch` and `WebFetch`, and `scripts/research/research.py:231` (`stage_collect`) merges what they return.
- The pipeline is one-shot. `STAGES` at `research.py:39` runs plan through report once. `--from` re-runs from a stage and clears everything after it (`clear_from`, `research.py:606`). Nothing re-searches later.
- Claim ids `C1..Cn` are assigned per run, so a re-run renumbers them.
- Source kinds are a fixed list of software-flavoured types (`SOURCE_KINDS`, `research.py:57`: paper, docs, blog, repo, news, forum, talk, other). There is no reliability or certainty grading. Verdicts are HOLDS, WEAK, REFUTED and UNSUPPORTED (`research.py:49`).
- The brief has `Source preferences` but no evidence types, cadence or retirement criteria (`templates/brief.md`).
- The runner already downloads pages with urllib and stores them like ingest (`sources/web-<topic>/`), so adding HTTP adapters needs no new runtime.
- The 2026-10-10 review found defects in the code this plan extends:
  - `parallel()` discards replies that already succeeded when one call fails (`scripts/runner/rc.py:168`).
  - The source limit is applied after claims are checked (`research.py:250`, KeyError).
  - `quote_found` accepts changed numbers and very short quotes (`research.py:215`).
  - `CLAIM_REF` misses grouped citations like `[C3, C7]` (`research.py:55`).
  - `extract_json` mis-pairs code fences (`rc.py:81`).
- The practices adopted below come from published methodology: Cochrane living systematic reviews, PRISMA 2020 and PRISMA-S, Wohlin's snowballing guidelines, GRADE, the NATO/Admiralty source grading, Heuer's Analysis of Competing Hypotheses, ICD 203 analytic standards, SIFT lateral reading, the ThoughtWorks Technology Radar and government horizon-scanning guides. A recent example of an automated living review is the ISPOR Europe 2026 poster on GenAI living evidence reviews: scheduled searches, incremental ingestion, a version-controlled evidence store, and change flags for human validation. These have not been ingested into an RC yet. WP-final runs the RC on its own method to check them.

## Adopted practices

Each row is a point this plan adopts and the mechanism that enforces it.

| Practice | Point adopted | RC mechanism | WP |
| --- | --- | --- | --- |
| Living systematic review | Saved searches re-run on a fixed cadence | `watch.json` with queries per adapter and question, `cadence`, `lastChecked` | WP4 |
| Living systematic review | Screen only what is new since the last search | `seen.json` keyed by DOI, canonical URL or adapter id, with first-seen date and decision | WP4 |
| Living systematic review | Update the conclusion only on material change | Refresh re-runs analyze, apply and report only when a verdict, an answer's certainty or a fit ring would change; otherwise the delta says "no material change" | WP4 |
| Living systematic review | Explicit living status and retirement criteria | Brief section `Living`: cadence, retire-when; topic status `living`, `paused`, `retired` | WP4 |
| Living systematic review | Version every published state | Each refresh commits `delta/<date>.md`; the report header shows version, last checked and last changed; git holds history | WP4 |
| PRISMA 2020 | Flow of identified, duplicates, screened, excluded with reasons, included | `screening.json` per candidate; the report appendix prints the flow counts | WP2 |
| PRISMA 2020 | Fixed eligibility criteria before screening | The brief's scope and out of scope become the screener's include/exclude criteria; each exclusion names the criterion | WP2 |
| PRISMA-S | Report every search reproducibly | `searches.json`: adapter, exact query, filters, date, result count | WP1 |
| Protocol registration | The protocol is fixed before searching, and changes are logged | The accepted brief is the protocol; edits after acceptance go to an `Amendments` section; a brief hash on every stage output makes later stages stale when the brief changes | WP4 |
| Snowballing (Wohlin) | Backward (references) and forward (citations) from included key works, iterated to saturation | `snowball` step through the OpenAlex adapter, depth-limited (default 1), each hop screened again | WP3 |
| Horizon scanning | Continuous scanning of weak signals across domains, not only the obvious one | Feed and page-watch adapters in `watch.json`; the planner must cover at least two adapter families when they exist | WP1, WP4 |
| Horizon scanning | Search deliberately for evidence of the opposite shift | The planner must add a disconfirming query for every hypothesis it expects; checked by the runner | WP2 |
| Horizon scanning | Time horizons | The brief's scope states the horizon (near, medium, long); the planner's recency filters follow it | WP2 |
| Horizon scanning | Signals weaken and are deprioritised | Staleness per evidence type (half-life); expired claims are re-checked on refresh | WP5 |
| GRADE | Certainty per answer: high, moderate, low, very low | `certainty` per question answer in the analysis, checked by the runner | WP5 |
| GRADE | Downgrade for risk of bias, inconsistency, indirectness, imprecision, publication bias; upgrade for large effects | Generalized for any domain: low source reliability, conflicting claims, evidence about a context unlike "Our needs", vague or small-sample evidence, one-sided sources (for example vendor-only). Every downgrade names its reason and claims | WP5 |
| Admiralty / NATO grading | Grade source reliability (A-F) separately from information credibility (1-6) | `reliability` on every source (researcher proposes with a reason, sceptics may challenge); `credibility` on every claim (judge) | WP5 |
| Evidence hierarchies | What counts as strong evidence depends on the domain | `catalog/evidence-types.json`: domain-agnostic types with a reliability ceiling and a half-life each, replacing `SOURCE_KINDS` | WP5 |
| SIFT lateral reading | Trace claims to the original; find better coverage | A claim from a secondary source carries `via`; for claims an answer relies on, collection must try to reach the primary source, and the sceptic flags untraced ones | WP5 |
| SIFT / CRAAP | Investigate the source | Reliability grades come with a reason; retracted works are excluded through the Crossref retraction check | WP3, WP5 |
| ACH (Heuer) | Enumerate competing hypotheses and score evidence against all of them | For questions with alternatives, the analysis outputs a hypothesis-by-claim matrix (consistent, inconsistent, neutral); the runner checks every hypothesis has disconfirming search coverage | WP6 |
| ACH (Heuer) | Weight diagnostic evidence; prefer the hypothesis with least inconsistent evidence | The judge reports diagnostic claims per question; the analysis ranks hypotheses by inconsistency, not by support | WP6 |
| Key assumptions check | List and test the assumptions an answer rests on | `assumptions` per answer; sceptics test them like claims | WP6 |
| ICD 203 | Calibrated estimative language and separate confidence | The report uses a fixed word scale (almost certain ... remote) mapped to certainty; the runner rejects unmapped words in answer headlines | WP6 |
| ICD 203 | Distinguish evidence from judgement | The report marks each sentence's basis: claim citation or "assessment" | WP6 |
| Technology Radar | Rings, plus "new" and "moved" markers over time | Fit rings keep a history; the delta and report show new and moved ideas | WP4 |
| Living evidence repository (ISPOR 2026) | Change flags for human validation | Flipped verdicts and moved rings are listed in the delta as "needs your review", like contested claims | WP4 |

## Affected scope

| Repository | Worktree | Read/write | Interfaces |
| --- | --- | --- | --- |
| research-center | local clone `Desktop/Code/research-center` | write | `./rc research` (new `refresh`, `watch`), `scripts/sources/` (new), `scripts/research/`, `scripts/runner/rc.py`, `catalog/adapters/` and `catalog/evidence-types.json` (new, templated), `templates/brief.md`, research skills, `docs/` |

## Invariants and decisions

- **Adapters run in the runner, never in an agent.** An adapter is a Python module in `scripts/sources/adapters/` with `search(query, filters, since) -> records`, plus optional `fetch(record) -> text` and `related(record, direction) -> records` for snowballing. A matching descriptor lives in `catalog/adapters/<id>.json`: `id`, `family` (scholarly, web, news, feed, reference, code, data, legal, regulatory, ...), `covers` (plain text for the planner), `evidenceTypes`, `queryHelp`, `watchable`, `needsKeyEnv`, `rateLimit`. The planner chooses adapters from these descriptors. It never learns of an adapter any other way.
- **One record shape.** Every adapter returns `{adapter, key, title, authors, date, url, doi?, evidenceType, abstract?, raw?}`. `key` is a stable id: DOI, else canonical URL, else adapter id. Duplicates across adapters merge on `key`. A record's text is stored only when it is screened in, under `sources/web-<topic>/` with the existing manifest and redaction path.
- **The general adapter set works for any topic and needs no key:** web (the existing researcher roles), openalex (scholarly works in all fields, plus references and citations), crossref (DOI metadata, retractions), wikipedia (orientation and reference lists, never evidence above reliability C), feed (RSS/Atom), page-watch (a URL whose changes are tracked), gdelt (news), openlibrary (books). Domain packs come later and add, never replace.
- **Collect becomes search → screen → snowball → read.** The runner runs the planned adapter queries. A screener role (new, read-only, batch input) includes or excludes each new record against the brief's criteria with a reason. The runner snowballs from included scholarly records. The researchers then extract claims from the included stored texts and also search the web as today. Quote verification applies to every claim the same way.
- **Stable claim ids.** A claim keeps its id across refreshes. New claims get the next free id. A claim whose page has disappeared or whose quote no longer matches is marked `drifted`, never renumbered or deleted.
- **Verdicts have history.** Each claim and idea keeps `history: [{date, verdict, run}]`. The current verdict is the last entry. Flips are delta material.
- **Evidence types are domain-agnostic and data, not code.** The initial `catalog/evidence-types.json`: dataset or primary data, systematic review, peer-reviewed study, preprint, official statistics, regulation or statute, court ruling, standard or specification, company filing, official documentation, book, journalism, vendor material, expert commentary, community forum, reference work. Each has a reliability ceiling and a half-life. An instance may edit them, and the validator checks the shape.
- **Refresh is cheap when nothing changed.** The runner runs adapter queries and drift checks without an agent. A refresh that finds nothing new and nothing expired costs zero agent calls and still commits an updated `lastChecked` and a one-line delta.
- **Budgets.** A new `budget.refreshCalls` (default 8). Screening is batched (up to 40 records per call). A refresh that would exceed the budget stops in a resumable state, as in `docs/decisions/0006-budgets-and-resume.md`.
- **No silent widening.** An adapter that errors or hits its rate limit is reported in the run and in `searches.json` (status, count 0). Its earlier records are kept, never deleted.
- **Tests never touch the network.** Each adapter ships recorded responses under `scripts/sources/fixtures/`, and its tests replay them. The Nix sandbox has no network anyway.
- New ADRs record these decisions: 0007 source adapters, 0008 living topics and refresh, 0009 evidence grading and certainty.

## Open questions

| Question | Impact | Owner/next evidence |
| --- | --- | --- |
| Which model should the screener use by default: a cheaper Claude model or the same as the researchers? | Cost of every refresh | Decided 2026-10-10: claude `sonnet`, changeable with `./rc roles set screener`. Revisit by measuring agreement against opus on a 100-record fixture |
| Default cadence: weekly, monthly, or derived from the shortest half-life in the brief's evidence types? | How current topics stay vs. calls spent | Decided 2026-10-10: derived from the shortest half-life of the brief's evidence types, clamped to weekly-quarterly; the user may override it at grilling |
| Should the claim store be per topic (v1) or shared across topics so one new paper updates every topic citing it? | Scope of WP5 and the refresh fan-out | Decided 2026-10-10: per topic in v1. Revisit after two living topics exist |
| OpenAlex and Crossref polite-pool contact email: from the instance settings or the git user email? | Rate limits; the email goes to a third party | Decided 2026-10-10: none by default (anonymous pool). An optional `research.contactEmail` setting, set only by the user |
| Do adapters fetch full text for papers (open-access PDFs through extract.py) in v1, or stay at abstracts? | Claim depth for scholarly topics | Decided 2026-10-10: abstracts in v1. Full text is decided after the WP8 dogfood topic; GROBID or Docling may be needed |
| Which domain packs first? | Proves the pack mechanism | Decided 2026-10-10: pubmed (medicine) and github (software), because they differ most |

## Work packages

| ID | Outcome | Write scope | Depends on | Completion check |
| --- | --- | --- | --- | --- |
| WP0 | Fix the review defects this plan builds on: `parallel()` keeps finished replies and the stage resumes per call; source limit applied before claim checks; quote check requires numbers and negations to match and a minimum of 6 words; grouped citations `[C3, C7]` parsed everywhere; `extract_json` handles tagged fences | `scripts/runner/rc.py`, `scripts/research/research.py`, tests | - | New regression test per defect; `research_test` and `providers_test` pass |
| WP1 | Adapter interface, registry and the general adapters (openalex, crossref, wikipedia, feed, page-watch, gdelt, openlibrary) with fixture tests; `searches.json` written for every query | `scripts/sources/`, `catalog/adapters/` templates, `flake.nix` checks | WP0 | `./rc sources search openalex "..."` prints normalized records from a fixture; each adapter's test replays fixtures offline |
| WP2 | Collect becomes search → screen → read: planner outputs structured adapter queries (with disconfirming queries and horizon), new screener role and skill, `screening.json` with reasons, PRISMA flow in the report appendix | `scripts/research/`, `.agents/skills/research-plan-sources`, new `research-screen`, `templates/agents/screener.json` | WP1 | On fixtures: excluded records name a scope criterion; flow counts add up; a plan without a disconfirming query is rejected |
| WP3 | Snowballing (backward and forward, depth-limited, screened per hop) and the retraction check | `scripts/sources/`, `scripts/research/` | WP2 | Fixture citation graph: a key work's reference and citer are found, screened and stored; a retracted DOI is excluded with reason "retracted" |
| WP4 | Living topics: brief `Living` and `Amendments` sections, `watch.json`, `seen.json`, stable claim ids, verdict and ring history, brief hash staleness, `./rc research refresh <topic>` and `refresh --due`, `delta/<date>.md`, topic status, report version header, scheduling notes in GUIDE.md | `scripts/research/`, `templates/brief.md`, `grill-research-topic`, `rc-research`, `GUIDE.md` | WP2 | Fixture scenario: refresh with no new records costs 0 calls and writes "no material change"; with one new contradicting record it adds a claim with the next id, re-judges, flips a verdict and lists it under "needs your review" |
| WP5 | Evidence grading: `catalog/evidence-types.json`, source reliability A-F, claim credibility 1-6, `via` and primary-source tracing, GRADE-style certainty with named downgrade reasons, staleness re-checks (refetch, quote still present, else `drifted`) | `scripts/research/`, research skills, `catalog/` template, validator | WP4 | Validator rejects an answer without certainty or a downgrade without a reason; an expired claim whose page changed is marked `drifted` and re-critiqued on refresh |
| WP6 | Analysis rigour: ACH matrix for questions with alternatives, key assumptions, diagnostic claims, calibrated estimative language and evidence-vs-assessment marking in the report | `research-analyze`, `research-judge`, `research-report`, `research-sceptic` skills, `research.py` checks | WP5 | Runner rejects a headline with an unmapped likelihood word and an ACH question whose hypotheses lack disconfirming coverage |
| WP7 | First domain packs (pubmed, github) to prove the mechanism, plus an adapter template for user-defined sites and APIs | `scripts/sources/adapters/`, `catalog/adapters/`, `rc-ingest`/`rc-help` skills | WP1 | A pack is enabled per instance without touching core code; the template adapter passes its fixture test |
| WP8 | Docs and dogfood: ADRs 0007-0009, architecture, glossary, README pipeline table, rc-help; then one live living topic outside software (proposal: "evidence on four-day work weeks") run, refreshed once and reviewed | `docs/`, `README.md`, skills | WP1-WP7 | `./rc validate` passes; the live topic has a report, one refresh delta and a PRISMA flow |

## Integration and verification

`./rc check` runs the new adapter, screening, refresh and grading tests offline against fixtures, plus the existing checks. Without Nix, run `./rc validate` and the Python tests named in `flake.nix`, and say that the Nix part was not verified. The live dogfood topic in WP8 is the end-to-end proof: plan, adapter search, screening, snowballing, claims, grading, critique, judgement, report, then one refresh with a delta.

## Failure, rollback and stop conditions

- An adapter failure or rate limit: the run continues with the other avenues, reports the failure, and keeps earlier records. If every planned non-web adapter fails, the run stops rather than silently becoming web-only.
- A refresh that would exceed `budget.refreshCalls`: stop in a resumable state.
- A brief amended after acceptance: later stages are stale. Refresh re-runs from plan and never reuses outputs built on the old brief.
- Each WP lands as its own commit series and leaves `./rc check` green. Reverting a WP's commits restores the previous pipeline, because existing topics without `watch.json` keep working as one-shot topics.

## Acceptance criteria

- A topic outside software produces a report whose sources come from at least two adapter families besides web search, with a PRISMA flow, reliability grades, certainty per answer and calibrated wording.
- `./rc research refresh` on an unchanged topic costs no agent calls. On a changed topic it produces a delta that lists new claims, flipped verdicts, moved rings and items needing the user's review, with stable claim ids.
- Every row in "Adopted practices" is enforced by a runner check, a validator rule or a role contract the runner checks.
- No adapter needs a stored credential, and no test needs the network.
- `./rc check` passes.

## Lifecycle closure

Not closed.
