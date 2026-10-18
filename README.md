# Research Center

An AI research assistant you run with your own Claude subscription, natively on Windows (or macOS and Linux), on any subject: medicine, law, markets, history, engineering, software. Point it at what you already know (your company's repos, Notion, Google Drive, documents, the books and papers you read), grill a research topic with it, and get back a report in which every claim is cited, graded, critiqued by sceptics and fitted to your own projects. A topic can stay living: the RC keeps searching, and tells you when the evidence changes.

```text
profile (type, tags) → ingest (optional) → grill → plan → search → screen → collect → analyze → critique → judge → apply → report → share
```

| Stage | What happens | Output |
| --- | --- | --- |
| profile | Whom the research serves: a company or a person, with a description and interest tags. A company profile may use only permissive licences, a personal one any. Each profile keeps its own sources and research | `profiles/<id>/profile.json` |
| ingest | Folders, repos, URLs, Notion and Drive become committed text (secrets redacted), one digest per source, and a cited profile of you or your company | `sources/`, `knowledge/` |
| grill | An agent turns your topic into numbered questions, scope, needs and success criteria, asking only what your profile cannot answer | `research/<topic>/brief.md` |
| plan | Hypotheses, a disconfirming search for each, adapter queries per question, exclusion criteria | `source-plan.md` |
| search | The runner queries the adapters (scholarly works, books, news, feeds, watched pages); every query logged | `searches.json` |
| screen | Each result included or excluded against the criteria, with a reason; references and citations of the key works followed and screened too; retractions dropped | `screening.md` |
| collect | Two researchers (Claude Opus and Sonnet) read the included records and search the web in parallel; every cited page is stored and every quote checked against it | `claims.md`, `sources/web-<topic>/` |
| analyze | Each question answered from the claims ledger; competing hypotheses weighed in a matrix; key assumptions named | `analysis.md` |
| critique | Two sceptics (Claude Opus and Sonnet) independently try to disprove every claim and assumption the analysis uses | `critique/` |
| judge | Claude settles the anonymous reviews, grades each claim's credibility and each answer's certainty; contested claims are flagged for you | `judgement.md` |
| apply | Surviving ideas ranked ADOPT, TRIAL, ASSESS or HOLD against your repos and needs | `fit.md`, `handoff.md` |
| report | The answer, citing only claims that survived, with calibrated likelihood words, the certainty of each answer and how the sources were found | `report.md` |
| share | The topic as one HTML page for people without the repository: bottom line, ideas by ring, certainty, the evidence charted, every claim linked to its source; a dashboard for the profile; published as a private claude.ai link | `rc report`, rc-share |

A brief with a cadence makes the topic **living**: `./rc research refresh` re-runs its searches, screens only what is new, re-derives the conclusions when new verified evidence arrives, and writes a delta of what changed and what needs your review.

Ideas worth acting on leave as a [Control Center](https://github.com/romank-foxcale/command_center_template) task plan (`handoff.md`). The RC itself never touches product code.

## Install

The same way as the Control Center kit, and it can sit next to it:

- Windows: in PowerShell (no administrator rights, no WSL), run `install\windows\install.ps1`. It installs git, the GitHub CLI, uv and Claude Code, and puts `rc-kit` on your PATH.
- macOS / Linux / WSL: `curl -fsSL https://raw.githubusercontent.com/romank-foxcale/research-center/main/install/install.sh | sh`

Then run `rc-kit doctor`. Step-by-step instructions for every tool are in [GUIDE.md](GUIDE.md).

## Creating an RC

```bash
rc-kit new my-project          # ~/Projects/my-project_RC, next to my-project_CC
rc-kit open my-project code    # or: cd ~/Projects/my-project_RC && claude
```

First prompt:

> Set up this Research Center. Use the grill-rc-bootstrap skill.

Without the kit, the manual way is:

```bash
mkdir my-project_RC
cd my-project_RC
git clone https://github.com/romank-foxcale/research-center rc_template
claude   # or codex, opencode
```

First prompt:

> Create a Research Center here. Read `rc_template/BOOTSTRAP.md`, treat `rc_template` as a read-only source and start grilling. If there is already research material here, migrate it without losing meaning.

After `./rc check` passes, delete `rc_template/` and commit the RC.

This template is public and holds no data. Your RC commits the text of everything you ingest, so **its remote must be private**. `./rc ingest` refuses to run otherwise.

| | Control Center | Research Center |
| --- | --- | --- |
| Install | `install.sh` → `~/.cc-kit`, `cc-kit` | `install.sh` → `~/.rc-kit`, `rc-kit` |
| Create | `cc-kit new <name>` → `<name>_CC` | `rc-kit new <name>` → `<name>_RC` |
| First prompt | Use the grill-cc-bootstrap skill | Use the grill-rc-bootstrap skill |
| Manual | `cc_template` clone + `BOOTSTRAP.md` | `rc_template` clone + `BOOTSTRAP.md` |
| Help, settings | `/cc-help`, `./cc settings` | `/rc-help`, `./rc settings` |
| Gate | `./cc check`, `./cc verify` | `./rc check` |
| Live runs | `./cc watch` | `./rc watch` |

## Commands

`./rc help` lists everything. The most used:

```text
./rc doctor                                   logins and tools
./rc profile new acme --name "Acme" --type company   a profile: whom the RC works for
./rc -p acme tags add "Japanese OCR"          an interest tag; or drop files into profiles/acme/inbox/ and run tags suggest
./rc -p acme scout                            technology cards: what is new for the profile's tags, and whether it fits
./rc home                                     the main screen: every profile's cards, one page each, ready to share
./rc -p acme ingest add ...                   work inside a profile (or set defaultProfile)
./rc ingest add git https://github.com/org/api --note "our main API"
./rc ingest add folder /mnt/c/Users/me/Papers --include '*.pdf'
./rc ingest add notion https://www.notion.so/... --depth 2
./rc ingest run                               fetch, digest, profile
./rc research new four-day-week --title "Does a four-day week keep output stable?"
./rc research accept four-day-week            after grilling
./rc research run four-day-week               then ./rc watch
./rc research refresh --due                   keep living topics current (schedule it)
./rc sources list                             adapters beyond web search
./rc sources search openalex "four-day work week" --since 2023-01-01
./rc sources enable medicine                  domain packs: medicine (PubMed), software (GitHub), news (Guardian, free key)
./rc sources new city-council --family regulatory --evidence-type regulation   your own adapter
./rc roles set judge --provider claude --model opus
./rc check
```

## How it stays honest

- Agents only read: every file is written by the runner, and access is enforced by CLI flags. Claude runs in `dontAsk` with an allow-list of read tools; Codex, where it is used, in its read-only sandbox.
- Every profile fact cites a stored source file, and every report claim cites a stored page whose quote was checked.
- Sceptics review independently. The judge sees them only as Review A, B, C. A claim one sceptic refuted and the judge kept is shown to you as contested.
- Questions with competing answers are weighed in a hypothesis matrix, every answer names its key assumptions, and the report says likelihood only on a fixed scale, marking what is evidence and what is assessment.
- Every source carries a reliability grade capped by its evidence type, every claim a credibility grade, and every answer a certainty (high to very low) with the named weaknesses that lowered it.
- `./rc check` validates every manifest, citation and report, and fails on any unredacted secret.

See [docs/index.md](docs/index.md) for the architecture and decisions.
