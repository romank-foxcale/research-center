# Research Center

An AI research assistant you run with your own Claude, ChatGPT and Cursor subscriptions. Point it at what you already know (your company's repos, Notion, Google Drive, documents, the books and papers you read), grill a research topic with it, and get back a report in which every claim is cited, critiqued by sceptics and fitted to your own projects.

```text
ingest (optional) → grill → plan → collect → analyze → critique → judge → apply → report
```

| Stage | What happens | Output |
| --- | --- | --- |
| ingest | Folders, repos, URLs, Notion and Drive become committed text (secrets redacted), one digest per source, and a cited profile of you or your company | `sources/`, `knowledge/` |
| grill | An agent turns your topic into numbered questions, scope, needs and success criteria, asking only what your profile cannot answer | `research/<topic>/brief.md` |
| plan | Where to search and why, per question | `source-plan.md` |
| collect | Claude and GPT search the web in parallel; every cited page is stored and every quote checked against it | `claims.md`, `sources/web-<topic>/` |
| analyze | Each question answered from the claims ledger, ideas compared | `analysis.md` |
| critique | Claude, GPT and Grok try to disprove every claim the analysis uses | `critique/` |
| judge | Grok settles the anonymous reviews; contested claims are flagged for you | `judgement.md` |
| apply | Surviving ideas ranked ADOPT, TRIAL, ASSESS or HOLD against your repos and needs | `fit.md`, `handoff.md` |
| report | The answer, citing only claims that survived | `report.md` |

Ideas worth acting on leave as a [Control Center](https://github.com/romank-foxcale/command_center_template) task plan (`handoff.md`). The RC itself never touches product code.

## Start

Requirements: Nix, Git, `gh` (logged in), and the CLIs of the subscriptions you use: `claude`, `codex`, `cursor-agent`. On Windows, run everything inside WSL. `rc.cmd` forwards to it.

```bash
git clone https://github.com/romank-foxcale/research-center
cd research-center
./rc bootstrap install ../my_RC
```

Then open a coding agent (Claude Code, Codex) in `../my_RC` and say "set up my research center". The `grill-rc-bootstrap` skill takes it from there: private remote, logins, models, budgets, and your first sources or topic.

The template is public and holds no data. Your instance commits the text of everything you ingest, so **its remote must be private**. `./rc ingest` refuses to run otherwise.

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
./rc roles set judge --provider claude --model opus
./rc check
```

## How it stays honest

- Agents only read: every file is written by the runner, and access is enforced by CLI flags. Claude runs in `dontAsk` with an allow-list, Codex in its read-only sandbox, Cursor in a throwaway snapshot with a deny config.
- Every profile fact cites a stored source file, and every report claim cites a stored page whose quote was checked.
- Sceptics review independently. The judge sees them only as Review A, B, C. A claim one sceptic refuted and the judge kept is shown to you as contested.
- `./rc check` validates every manifest, citation and report, and fails on any unredacted secret.

See [docs/index.md](docs/index.md) for the architecture and decisions.
