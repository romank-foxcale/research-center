# Research Center

An AI research assistant you run with your own Claude, ChatGPT and Cursor subscriptions. Point it at what you already know (your company's repos, Notion, Google Drive, documents, the books and papers you read), grill a research topic with it, and get back a report in which every claim is cited, critiqued by sceptics and fitted to your own projects.

```text
ingest (optional) → grill → plan → search → screen → collect → analyze → critique → judge → apply → report
```

| Stage | What happens | Output |
| --- | --- | --- |
| ingest | Folders, repos, URLs, Notion and Drive become committed text (secrets redacted), one digest per source, and a cited profile of you or your company | `sources/`, `knowledge/` |
| grill | An agent turns your topic into numbered questions, scope, needs and success criteria, asking only what your profile cannot answer | `research/<topic>/brief.md` |
| plan | Hypotheses, a disconfirming search for each, adapter queries per question, exclusion criteria | `source-plan.md` |
| search | The runner queries the adapters (scholarly works, books, news, feeds, watched pages); every query logged | `searches.json` |
| screen | Each result included or excluded against the criteria, with a reason; references and citations of the key works followed and screened too; retractions dropped | `screening.md` |
| collect | Claude and GPT read the included records and search the web in parallel; every cited page is stored and every quote checked against it | `claims.md`, `sources/web-<topic>/` |
| analyze | Each question answered from the claims ledger, ideas compared | `analysis.md` |
| critique | Claude, GPT and Grok try to disprove every claim the analysis uses | `critique/` |
| judge | Grok settles the anonymous reviews; contested claims are flagged for you | `judgement.md` |
| apply | Surviving ideas ranked ADOPT, TRIAL, ASSESS or HOLD against your repos and needs | `fit.md`, `handoff.md` |
| report | The answer, citing only claims that survived | `report.md` |

A brief with a cadence makes the topic **living**: `./rc research refresh` re-runs its searches, screens only what is new, re-derives the conclusions when new verified evidence arrives, and writes a delta of what changed and what needs your review.

Ideas worth acting on leave as a [Control Center](https://github.com/romank-foxcale/command_center_template) task plan (`handoff.md`). The RC itself never touches product code.

## Install

The same way as the Control Center kit, and it can sit next to it:

- Windows: in PowerShell as administrator, run `install/windows/install.ps1 -Tools claude,codex,cursor`
- macOS / Linux / WSL: `curl -fsSL https://raw.githubusercontent.com/romank-foxcale/research-center/main/install/install.sh | bash -s -- --tools claude,codex,cursor`

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
claude   # or codex, opencode, cursor .
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
./rc ingest add git https://github.com/org/api --note "our main API"
./rc ingest add folder /mnt/c/Users/me/Papers --include '*.pdf'
./rc ingest add notion https://www.notion.so/... --depth 2
./rc ingest run                               fetch, digest, profile
./rc research new agent-memory --title "Long-term memory for coding agents"
./rc research accept agent-memory             after grilling
./rc research run agent-memory                then ./rc watch
./rc research refresh --due                   keep living topics current (schedule it)
./rc sources list                             adapters beyond web search
./rc sources search openalex "four-day work week" --since 2023-01-01
./rc roles set judge --provider claude --model opus
./rc check
```

## How it stays honest

- Agents only read: every file is written by the runner, and access is enforced by CLI flags. Claude runs in `dontAsk` with an allow-list, Codex in its read-only sandbox, Cursor in a throwaway snapshot with a deny config.
- Every profile fact cites a stored source file, and every report claim cites a stored page whose quote was checked.
- Sceptics review independently. The judge sees them only as Review A, B, C. A claim one sceptic refuted and the judge kept is shown to you as contested.
- Questions with competing answers are weighed in a hypothesis matrix, every answer names its key assumptions, and the report says likelihood only on a fixed scale, marking what is evidence and what is assessment.
- Every source carries a reliability grade capped by its evidence type, every claim a credibility grade, and every answer a certainty (high to very low) with the named weaknesses that lowered it.
- `./rc check` validates every manifest, citation and report, and fails on any unredacted secret.

See [docs/index.md](docs/index.md) for the architecture and decisions.
