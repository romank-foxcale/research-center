# rc-bootstrap: a Research Center template that ingests what the user knows, grills a topic and produces critiqued, applicable research

Lifecycle: completed
Planning status: accepted

## Outcome

`research-center` is a public template, seeded like `command_center_template`, from which a user creates a private Research Center (RC) instance. An instance:

1. **Ingests** (optional, repeatable) the sources the user points at - local folders, Git repos, URLs, Notion, Google Drive - into committed extracted text, per-source digests and a cited profile of the user or company.
2. **Grills** the user on a research topic, evidence-first: it never asks what the profile already answers, and starts from scratch when nothing was ingested.
3. **Researches** the topic in a fixed pipeline: source plan, collection, claim extraction, analysis and comparison, critique by sceptics, anonymous judging.
4. **Applies** the surviving ideas to the user's repos as a fit assessment, and turns accepted ideas into a draft plan the CC can take over.
5. Delivers one **research report per topic**, every claim cited.

## Non-goals

- The RC never writes or changes product code, and never builds prototypes. Code work goes to a CC through a handoff the user carries over.
- No credential storage. Notion and Drive go through the user's own provider logins.
- No newsletter scheduling and no publishing to external services in v1. Reports stay in the instance repo.
- No shared library with the CC. Provider and runner code is copied (see decisions).

## Evidence and current behavior

- `command_center_template@6489510` runs headless councils under the user's subscription logins through `scripts/council/providers.py`: `claude`, `codex` and `cursor` (Grok). Access is enforced by CLI flags or provider config, never by prompts (CC ADR 0007, 0014).
- On 2026-10-09, `claude mcp list` in WSL showed the claude.ai connectors Notion, Google Drive, Slack, Gmail, Trello, Google Sheets and Claude Docs as connected. `codex mcp list` showed none. `cursor-agent` is installed.
- The CC's knowledge layout (atomic notes with `id`, `status`, `evidence`, `relations`, `verified_at`, `superseded`), its validator, its live run events with `watch`, and its sceptic skill (`thread-sceptic`, burden of proof on the claim) are proven and reusable.
- The remote `github.com/romank-foxcale/research-center` was empty and public on 2026-10-09.

## Affected scope

| Repository | Worktree | Read/write | Interfaces |
| --- | --- | --- | --- |
| research-center | local clone `../research-center` | write | `./rc` CLI, flake apps/checks, skills |
| command_center_template | none | read (copy source) | `scripts/council/*`, `scripts/events.py`, `scripts/validate-knowledge.py`, skills `thread-sceptic`, `lean-code`, hook setup |

## Invariants and decisions

- **Template vs instance.** The template ships no sources, digests or reports. Each instance is its own **private** repo. `./rc ingest` refuses to run when `origin` is public; the check goes through `gh repo view --json visibility`, and an unknown result also refuses.
- **Storage.** Sources are committed as extracted text (Markdown with a page or section map) under `sources/<source-id>/`. A manifest records the origin, kind, fingerprint and fetch time. Original binaries (PDF, EPUB, DOCX, slides) are never committed.
- **Secrets.** Before anything is written under `sources/`, a scanner replaces each detected secret with `[REDACTED:<kind>]` and adds an entry to `sources/<source-id>/redactions.md` (kind and location, never the value). A check fails if a known secret pattern appears anywhere in `sources/`.
- **Access.** Notion and Drive ingest run as a Claude-only role whose allowed tools are only the read and search tools of those connectors, set by CLI flags. Web collection uses each provider's own search tool. Folders and repos are read by RC scripts, not by agents.
- **Roles mirror the CC council.** Claude and GPT research and analyze in parallel, Grok (Cursor, read-only) judges anonymous labels, and Claude, GPT and Grok all critique. Each role's provider and model is configured in `catalog/agents/<role>.json`.
- **Copied, not shared.** Provider and runner code is copied from `command_center_template@6489510`. The origin commit is recorded in an ADR, so later syncs are deliberate diffs, not drift.
- **Same discipline as the CC.** Nix and Python, `./rc` entry with the WSL route, executable processes in flake apps and checks, atomic English notes, no AI attribution, skills edited in `.agents/skills/` and synced.
- **Profile is cited.** Every profile note links its claims to `sources/` paths. A digest or profile claim without evidence fails validation.
- **Handoff, not intrusion.** The apply stage writes `research/<topic>/handoff.md` in the CC plan format. The RC never writes into a CC. The user runs `./cc plan create` there with it.

## Open questions

| Question | Impact | Owner/next evidence |
| --- | --- | --- |
| Do `codex exec` and `cursor-agent --print` expose web search headlessly, and through which flags? | Whether GPT and Grok can collect, or only analyze collected text | Resolved 2026-10-09. `codex --search exec` searches the web (probed). Cursor has no proven web-only permission, so Grok judges and critiques only: docs/debt/cursor-no-web.md |
| Can headless Claude reach Notion and Drive with reading tools only? | Ingest without stored credentials | Resolved 2026-10-09. The connectors load through ToolSearch, and `dontAsk` with an allow-list refused an unlisted Notion tool and Write (probed). The live smoke run read 2 Notion pages: docs/decisions/0003-read-only-agents.md |
| How faithfully does the Drive connector return Google Docs, Sheets and Slides? | Ingest quality for Drive | Open. It is model-transcribed like Notion: docs/debt/connector-transcription.md |
| Ingest budget: how many model calls are allowed per run before sampling kicks in? | Subscription rate limits on large corpora | Decided: 60 ingest and 24 research calls by default, a hard stop that can be resumed, no silent sampling: docs/decisions/0006-budgets-and-resume.md |
| Book and paper text committed in a private repo | Copyright stays the user's responsibility | Stated in docs/decisions/0002-committed-extracted-sources.md; no technical control |

## Work packages

| ID | Outcome | Write scope | Depends on | Completion check |
| --- | --- | --- | --- | --- |
| WP1 | Skeleton: `flake.nix`, `./rc` + `rc.cmd`, `AGENTS.md`/`CLAUDE.md`, `docs/index.md`, knowledge validator, agents sync and rule hooks, ADRs for the decisions above | repo root, `docs/`, `scripts/`, `.agents/` | - | `./rc check` passes on the empty template |
| WP2 | Providers, runner, events and `./rc watch` copied and adapted, role catalog, CLI web-search probes recorded as notes | `scripts/runner/`, `catalog/agents/`, `docs/` | WP1 | Copied provider tests pass under `./rc check` |
| WP3 | `./rc ingest add\|run\|list\|remove`: folder, git, url, notion and gdrive adapters, text extraction, secret redaction, public-remote guard, fingerprints for incremental runs, map digests, reduce profile | `scripts/ingest/`, `sources/`, `knowledge/` | WP2 | On a fixture corpus with a planted fake token: text committed, token redacted and reported, profile notes cited; a re-run with no changes does nothing |
| WP4 | `grill-research-topic` skill and `./rc research new <topic>` produce `research/<topic>/brief.md` (questions, scope, success criteria, "our needs") | `.agents/skills/`, `scripts/research/` | WP3 | Grilling with a profile skips questions it answers; without a profile it starts from scratch |
| WP5 | `./rc research run <topic>`: source plan, collection (stored like ingest), claims with evidence, analysis and comparison, critique by sceptics, anonymous judge, `report.md` | `scripts/research/`, `.agents/skills/` | WP2, WP4 | Every report claim cites a source path; the critique section lists refuted claims |
| WP6 | Apply stage: fit assessment per idea against ingested repos, `handoff.md` in CC plan format for accepted ideas | `scripts/research/`, `.agents/skills/` | WP5 | The handoff is the CC's templates/task-plan.md filled in (`Lifecycle: active`, every heading, `Not closed.`), naming repos by remote, so it can be copied into a CC's plans/active |
| WP7 | Template mechanics: `grill-rc-bootstrap` skill, instance materialization, `rc-help` skill, README | repo root, `.agents/skills/` | WP1-WP6 | A fresh instance made from the template ingests, grills and runs end to end |

## Integration and verification

`./rc check` covers the Nix checks, the knowledge validator, the Python unit tests and the secret-pattern check over `sources/`. The end-to-end acceptance run uses a fixture corpus: this CC template, two articles and one Notion page.

## Failure, rollback and stop conditions

- A provider logged out or a CLI flag broken: the run fails. It never falls back to another provider or model.
- A scanner error, or the remote's visibility can't be determined: ingest stops before writing.
- The ingest budget is exceeded: the run stops with a resumable state. It never silently truncates.

## Acceptance criteria

- From the template, a private instance can ingest folders, repos, URLs, Notion and Drive, and produce a cited profile.
- Grilling uses the profile, and works without one.
- A research run produces a report in which every claim is cited, critiqued and judged, with a fit assessment against the user's repos and a CC-ready handoff.
- No secret, credential or original binary is ever committed. Ingest into a public remote is refused.
- `./rc check` passes.

## Lifecycle closure

- state: completed
- date: 2026-10-10
- evidence: All 7 flake checks pass; a live smoke instance ingested a git repo, a web page and 2 Notion pages (5 agent calls, 26 cited profile notes) and ran the full research pipeline (10 agent calls, 37 claims from 11 stored sources, 30 quotes verified, report and CC handoff) and validated
