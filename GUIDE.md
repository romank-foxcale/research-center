# Research Center: setup and usage guide

A **Research Center (RC)** is a git repo that does research with your own AI subscriptions. It is the knowledge counterpart of a [Control Center](https://github.com/romank-foxcale/command-center): you install it, create it and open it the same way.

- **It learns what you know.** Point it at your folders, repos, web pages, Notion and Google Drive. It commits their text (secrets redacted), digests each source, and builds a cited profile of you or your company.
- **It grills you on a topic.** Before any search, an agent turns "research X" into numbered questions, scope, needs and success criteria. It only asks what your profile can't answer.
- **It researches with several models.** Claude and GPT search the web independently, and every cited page is stored with its quote checked. Claude, GPT and Grok then try to disprove each claim, and an anonymous judge settles them.
- **It applies the results to your work.** Surviving ideas are ranked ADOPT, TRIAL, ASSESS or HOLD against your repos. The ones worth acting on become a Control Center task plan. The RC never touches code.

Everyone creates **their own RC** and uses **their own accounts**. The RC holds no credentials: roles call the `claude`, `codex` and `cursor-agent` CLIs with your logins, and Notion and Drive are read through your claude.ai connectors.

| Role in the pipeline | Default provider | Your subscription |
|---|---|---|
| Ingest (digests, profile, Notion/Drive reader), planner, analyst, applier, reporter, one researcher, one sceptic | `claude` | Claude Pro / Max / Team / Enterprise |
| One researcher, one sceptic | `codex` | ChatGPT plan |
| Judge, one sceptic | `cursor-agent` (Grok) | Cursor plan |

Missing a subscription? Move its roles to one you have (see [Settings](#5-everyday-work)).

---

## 1. Install

### Windows (WSL2)

Everything runs inside **WSL2** (Linux on Windows), because Nix doesn't run on Windows natively.

1. Open **PowerShell as administrator** (right-click → *Run as administrator*).
2. Download and run the installer:

   ```powershell
   irm https://raw.githubusercontent.com/romank-foxcale/research-center/main/install/windows/install.ps1 -OutFile $env:TEMP\rc-install.ps1
   powershell -ExecutionPolicy Bypass -File $env:TEMP\rc-install.ps1 -Tools claude,codex,cursor
   ```

   `-Tools` is optional. It installs those command-line tools inside WSL: `claude`, `codex`, `cursor` (cursor-agent) and `opencode`. Leave out the ones you don't use.
3. If WSL wasn't installed yet, the script installs it, and Ubuntu asks for a Linux username and password. Then run the second command again (no admin needed this time). Already have the Control Center kit? WSL, Nix and the tools are already there, so this step is quick.
4. The script does the rest inside Ubuntu: Nix with flakes, the GitHub CLI, the kit in `~/.rc-kit`, and the `rc-kit` command.

> **Keep your projects inside Linux** (`~/Projects`), never under `/mnt/c/...`.

### macOS

```bash
curl -fsSL https://raw.githubusercontent.com/romank-foxcale/research-center/main/install/install.sh | bash -s -- --tools claude,codex,cursor
```

### Log in once

```bash
gh auth login          # ingest asks GitHub whether your RC's remote is private
claude auth login      # or open claude once and sign in
codex login
cursor-agent login
```

### Check it worked

Open a **new** terminal (Ubuntu on Windows):

```bash
rc-kit doctor
```

Everything under *Required* must say `ok`. You need at least one research provider (claude or codex) logged in.

---

## 2. Create your Research Center

```bash
rc-kit new my-project
```

This creates `~/Projects/my-project_RC/`, its own git repo, next to your Control Centers:

```
~/Projects/
├── my-project_CC/        ← code: build, test, councils (its repos/ and worktrees/ inside)
└── my-project_RC/        ← knowledge: ingest, research, reports
```

Each project keeps everything it uses inside its own folder; nothing is shared between them. To ingest a repo, give the RC its URL.

`rc-kit list` shows your RCs and their status (`discovery` → `adapting` → `ready`).

> **Your RC commits the text of everything you ingest, so its remote must be private.** `./rc ingest` refuses to run when the remote is public or its visibility can't be checked.

---

## 3. Open it in your AI tool

Exactly as for a Control Center: `rc-kit open my-project code` (VS Code), `rc-kit open my-project cursor`, `cd ~/Projects/my-project_RC && claude` (or `codex`, `opencode`). In Claude Code desktop on Windows, choose **WSL → Ubuntu** and open `\\wsl.localhost\Ubuntu\home\<your-linux-user>\Projects\my-project_RC`. The Control Center's GUIDE.md, section 3, has the details for each tool.

---

## 4. First session: set the RC up

Type into your tool's chat:

> Set up this Research Center. Use the grill-rc-bootstrap skill.

The agent sets the private remote, checks your logins, moves roles off any subscription you don't have, agrees the budgets with you, and runs `./rc check`. When it's done, `research-center.json` has status `ready`.

You can also call the skill directly: `/grill-rc-bootstrap` in Claude Code and Cursor, `$grill-rc-bootstrap` in Codex.

---

## 5. Everyday work

Not sure which skill fits? Ask "what can the RC do?" or type `/rc-help`.

**Teach it what you know** (optional, repeatable):

> Point the RC at our repos and the Engineering space in Notion.

or directly:

```bash
./rc ingest add git https://github.com/acme/api --note "our main API"
./rc ingest add folder ~/Papers --include '*.pdf' --note "papers I keep coming back to"
./rc ingest add notion https://www.notion.so/acme/Engineering-... --depth 2
./rc ingest add gdrive 'search:architecture decision'
./rc ingest run        # then ./rc watch to follow it
```

**Research something:**

> Research how we could add long-term memory to our support bot.

The `grill-research-topic` skill writes the brief with you, then `rc-research` runs it:

```bash
./rc research run support-memory    # plan → collect → analyze → critique → judge → apply → report
./rc watch                          # live: stages, what each agent says, stalls
```

Read `research/<topic>/report.md`. Ideas ranked ADOPT or TRIAL come with `research/<topic>/handoff.md`: copy it into your Control Center's `plans/active/` and refine it there with `grill-task-planning`.

| Command | What it does |
|---|---|
| `./rc check` | Run every check: tests, notes, manifests, report citations, secret scan |
| `./rc validate` | The same validators without Nix |
| `./rc doctor` | Check Nix, gh and the claude, codex and cursor-agent logins |
| `./rc settings` | Status, budgets, limits, and which provider and model each role uses |
| `./rc roles set <role> --provider claude --model opus` | Move a role to another provider or model |
| `./rc ingest list` | Sources, file counts, last fetch, whether each digest is fresh |
| `./rc research list` / `show <topic>` | Topics and their stages |
| `./rc research run <topic> --from judge` | Redo a stage and everything after it |
| `./rc plan list` | Plans for changing the RC itself |
| `./rc agents sync` | After editing a skill in `.agents/skills/`, copy it to `.claude/skills/` |

**From Windows without opening Ubuntu:** the `rc.cmd` launcher runs the same commands inside WSL. In PowerShell type `.\rc check`, in cmd `rc check`. With several distributions installed, set `RC_WSL_DISTRO`.

**Budgets:** each run has a cap on agent calls (`budget.ingestCalls`, `budget.researchCalls` in `research-center.json`). Reaching it stops the run and keeps the finished work; running again resumes it.

---

## 6. Migrating an existing research setup

If you already keep research somewhere (a notes folder, an Obsidian vault, reading lists, earlier reports):

```bash
mkdir -p ~/Projects/old-research_RC && cd ~/Projects/old-research_RC
git clone ~/.rc-kit rc_template
```

Open that folder in your tool and say:

> Migrate my research into the Research Center format. Read `rc_template/BOOTSTRAP.md`, treat `rc_template` as read-only, and use the grill-rc-bootstrap skill.

The agent inventories your material without changing it, then brings it in as ingest sources one slice at a time. When it's done, delete `rc_template/`.

---

## 7. Updating the kit

```bash
rc-kit update
```

This updates `~/.rc-kit` only. Existing RCs are separate repos and never change behind your back. To pull a kit improvement into an RC, ask your agent to compare the RC with `~/.rc-kit` and bring over the change.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `ingest ... must be private` | Make the remote private on GitHub, or (non-GitHub) set `privateRemoteConfirmed` after checking it yourself. |
| `role ...: claude not logged in` | `claude auth login` (or `codex login`, `cursor-agent login`), or move the role: `./rc roles set`. |
| Notion or Drive source reads nothing | Connect Notion or Google Drive in claude.ai for the same account; `claude mcp list` must show it connected. |
| `agent call budget ... reached` | Run again to resume, or pass `--budget N` for one run. |
| `exceeds maxSourceBytes` | Narrow the source with `--include`/`--exclude`, or raise `ingest.maxSourceBytes`. |
| `rc-kit: command not found` | Open a new terminal, or run `source ~/.bashrc`. |
| Everything is very slow | Your RC is under `/mnt/c`. Move it to `~/Projects`. |
| Nix can't see a new file | Nix only sees files git knows about: `git add <file>`. |
