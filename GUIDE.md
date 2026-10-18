# Research Center: setup and usage guide

A **Research Center (RC)** is a git repo that does research with your own AI subscription. It is the knowledge counterpart of a [Control Center](https://github.com/romank-foxcale/command-center), and it runs natively on Windows (or macOS and Linux) with no WSL.

- **It learns what you know.** Point it at your folders, repos, web pages, Notion and Google Drive. It commits their text (secrets redacted), digests each source, and builds a cited profile of you or your company.
- **It grills you on a topic.** Before any search, an agent turns "research X" into numbered questions, scope, needs and success criteria. It only asks what your profile can't answer.
- **It researches with independent agents.** It searches scholarly databases, news, books, feeds and the web. Two researchers on different Claude models work independently, and every cited page is stored with its quote checked. Two sceptics then try to disprove each claim, and an anonymous judge settles them.
- **It applies the results to your work.** Surviving ideas are ranked ADOPT, TRIAL, ASSESS or HOLD against your repos. The ones worth acting on become a Control Center task plan. The RC never touches code.

Everyone creates **their own RC** and uses **their own accounts**. The RC holds no credentials: roles call the `claude` CLI with your login, and Notion and Drive are read through your claude.ai connectors.

| Role in the pipeline | Default | Your subscription |
|---|---|---|
| Ingest, planner, screener, analyst, judge, applier, reporter, researchers, sceptics | `claude` (Opus and Sonnet) | Claude Pro / Max / Team / Enterprise |
| Optional: a researcher or sceptic on GPT | `codex` (macOS, Linux or WSL only for now) | ChatGPT plan |

---

## 1. Install

### Windows

No WSL and no administrator rights. In PowerShell:

```powershell
irm https://raw.githubusercontent.com/romank-foxcale/research-center/main/install/windows/install.ps1 -OutFile $env:TEMP\rc-install.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\rc-install.ps1
```

It installs git, the GitHub CLI, uv and Claude Code (with winget and Claude's official installer), clones the kit to `%USERPROFILE%\.rc-kit`, and puts `rc-kit` on your PATH. Add `-Tools claude,codex` for the Codex CLI too. Re-running is safe: it skips what is there.

### macOS, Linux, WSL

```bash
curl -fsSL https://raw.githubusercontent.com/romank-foxcale/research-center/main/install/install.sh | sh
```

### Log in once

```bash
gh auth login          # ingest asks GitHub whether your RC's remote is private
claude auth login      # or open claude once and sign in
```

### Check it worked

Open a **new** terminal:

```bash
rc-kit doctor
```

Everything under *Required* must say `ok`.

---

## 2. Create your Research Center

```bash
rc-kit new my-project
```

This creates `my-project_RC` in your projects folder (`%USERPROFILE%\Projects` on Windows, `~/Projects` elsewhere), its own git repo, next to your Control Centers:

```
Projects/
├── my-project_CC/        ← code: build, test, councils
└── my-project_RC/        ← knowledge: ingest, research, reports
```

Each project keeps everything it uses inside its own folder; nothing is shared between them. To ingest a repo, give the RC its URL.

`rc-kit list` shows your RCs and their status (`discovery` → `adapting` → `ready`).

> **Your RC commits the text of everything you ingest, so its remote must be private.** `rc ingest` refuses to run when the remote is public or its visibility can't be checked.

---

## 3. Open it in your AI tool

`rc-kit open my-project claude` starts Claude Code in it; `rc-kit open my-project code` opens VS Code. In Claude Code desktop, open the folder `%USERPROFILE%\Projects\my-project_RC`.

Inside the RC, run commands as `.\rc <command>` in PowerShell, `rc <command>` in cmd, and `./rc <command>` in Git Bash, macOS and Linux. Agents use `./rc`: Claude Code runs commands through Git Bash on Windows. The first command creates the RC's Python environment with uv, which takes a few seconds once.

---

## 4. First session: set the RC up

Type into your tool's chat:

> Set up this Research Center. Use the grill-rc-bootstrap skill.

The agent sets the private remote, checks your logins, moves roles off any subscription you don't have, agrees the budgets with you, and runs `./rc check`. When it's done, `research-center.json` has status `ready`.

You can also call the skill directly: `/grill-rc-bootstrap` in Claude Code and Cursor, `$grill-rc-bootstrap` in Codex.

---

## 5. Everyday work

Not sure which skill fits? Ask "what can the RC do?" or type `/rc-help`.

**Profiles.** The RC works for profiles: a company, a product line, or you personally. Each has a type, a description, interest tags, and its own sources and topics, and research in one never sees another's material. A company profile may use only permissive licences (MIT, Apache-2.0, BSD and similar); a personal one may use any.

> Create a profile for our company. Use the grill-profile skill.

The agent creates `profiles/<id>/`, asks whether it is a company or personal profile, reads what you point it at (your website, product repos), and writes a short description. A company with products can also get a longer `scope.md`. Then work in it with `./rc -p <id> ...`, or set `defaultProfile` in `research-center.json`.

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
./rc research run support-memory    # plan → search → screen → collect → analyze → critique → judge → apply → report
./rc watch                          # live: stages, what each agent says, stalls
```

Read `research/<topic>/report.md`, or see it as a page: `./rc report <topic>` writes `.rc-local/reports/<topic>.html`, and `./rc report` writes a dashboard of every topic (`index.html`) with their pages beside it. To show it to someone without the repository:

> Share the support-memory research with my CTO. Use the rc-share skill.

The agent builds the page, tells you what it says, and after your yes publishes it as a private claude.ai link. Only you can open it until you share it from the page's Share menu. Sharing again later updates the same link.

Ideas ranked ADOPT or TRIAL come with `research/<topic>/handoff.md`: copy it into your Control Center's `plans/active/` and refine it there with `grill-task-planning`.

| Command | What it does |
|---|---|
| `./rc check` | Run every check: tests, notes, manifests, report citations, secret scan |
| `./rc validate` | The validators only, without the test suites |
| `./rc doctor` | Check Python, git, uv, gh and the claude and codex logins |
| `./rc profile list` / `show <id>` / `new <id> --name "..." --type company` / `edit <id>` | The profiles: name, type, description, tags |
| `./rc -p <id> tags list` / `add "<tag>"` / `remove` / `rename` | A profile's interest tags: what the scout searches for |
| `./rc -p <id> tags suggest` / `accept <tag>...` / `reject <tag>...` | Tags proposed from the profile's material, each with a reason |
| `./rc -p <id> scout` | Scout: discovery, then triage, technology cards and a sceptic check (about 12 agent calls); `scout cards` lists them, `scout dismiss <card>` closes one |
| `./rc -p <id> scout discover` | What is new for the profile's tags on GitHub, arXiv and OpenAlex since the last run; no agent calls |
| `./rc -p <id> <command>` | Run ingest, research, report, tags, scout or watch in one profile |
| `./rc settings` | Status, budgets, limits, and which provider and model each role uses |
| `./rc roles set <role> --provider claude --model opus` | Move a role to another provider or model |
| `./rc ingest list` | Sources, file counts, last fetch, whether each digest is fresh |
| `./rc research list` / `show <topic>` | Topics and their stages |
| `./rc home` | The main screen: every profile's tags and technology cards, one page per card (`.rc-local/reports/home/index.html`); share it with the rc-share skill |
| `./rc report [<topic>]` | A topic as one HTML page, or the dashboard of every topic, in `.rc-local/reports/` |
| `./rc research run <topic> --from judge` | Redo a stage and everything after it |
| `./rc sources packs` / `enable <pack>` | Domain packs: medicine (PubMed), software (GitHub), news (The Guardian; set GUARDIAN_API_KEY to a free Open Platform key) |
| `./rc sources new <id> --family F --evidence-type T` | Scaffold your own adapter for a site or API; `./rc sources test <id>` checks it |
| `./rc research refresh <topic>` | Re-search a living topic and write what changed to `research/<topic>/delta/<date>.md` |
| `./rc research refresh --due` | Refresh every living topic whose cadence has elapsed |
| `./rc research pause\|resume\|retire <topic>` | Stop refreshing for a while, start again, or for good |
| `./rc plan list` | Plans for changing the RC itself |
| `./rc agents sync` | After editing a skill in `.agents/skills/`, copy it to `.claude/skills/` |

**Budgets:** each run has a cap on agent calls (`budget.ingestCalls`, `budget.researchCalls`, `budget.refreshCalls` in `research-center.json`). Reaching it stops the run and keeps the finished work; running again resumes it.

**Keep a topic living.** A brief whose `## Living` section has a cadence (weekly, monthly, quarterly, or derived from the plan's horizon) becomes living after its first run. Each refresh re-runs the saved adapter searches since the last check and screens only what is new. A refresh that finds nothing costs no agent call. When new quote-verified evidence arrives, the analysis, critique, judgement, fit and report are re-derived and the version goes up. Read `delta/<date>.md`: its **Needs your review** section lists flipped verdicts, moved rings and newly contested claims. Refreshes run your own logged-in CLIs, so the machine must be on. Schedule `--due` daily or weekly; it skips topics that are not due, paused or retired:

```powershell
# Windows Task Scheduler
schtasks /create /sc weekly /d MON /st 07:00 /tn rc-refresh /tr "cmd /c cd /d %USERPROFILE%\Projects\my-project_RC && rc research refresh --due >> .rc-local\refresh.log 2>&1"
```

```bash
# macOS / Linux: crontab -e
0 7 * * 1  cd ~/Projects/my-project_RC && ./rc research refresh --due >> .rc-local/refresh.log 2>&1
```

Changing a living brief's questions, scope or needs stops its refreshes: log the change under `## Amendments`, and `./rc research run <topic>` redoes the research from plan as the next version.

---

## 6. Migrating an existing research setup

If you already keep research somewhere (a notes folder, an Obsidian vault, reading lists, earlier reports):

```bash
mkdir ~/Projects/old-research_RC
cd ~/Projects/old-research_RC
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

This updates the kit only. Existing RCs are separate repos and never change behind your back. To bring an RC up to the kit, commit its work, then:

```bash
rc-kit upgrade my-project               # scripts, skills, templates, settings and roles that are new
rc-kit upgrade my-project --reset-roles # also take the kit's default (Claude-only) pipeline roles
```

It refuses an RC with uncommitted changes, never touches sources, knowledge or research, and prints what it changed. Review it with `git diff` and commit.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `ingest ... must be private` | Make the remote private on GitHub, or (non-GitHub) set `privateRemoteConfirmed` after checking it yourself. |
| `role ...: claude not logged in` | `claude auth login` (or `codex login`), or move the role: `./rc roles set`. |
| Notion or Drive source reads nothing | Connect Notion or Google Drive in claude.ai for the same account; `claude mcp list` must show it connected. |
| `agent call budget ... reached` | Run again to resume, or pass `--budget N` for one run. |
| `exceeds maxSourceBytes` | Narrow the source with `--include`/`--exclude`, or raise `ingest.maxSourceBytes`. |
| `rc-kit: command not found` | Open a new terminal (the installer added it to your PATH). |
| `uv: command not found` | Re-run the installer, or install uv: `winget install astral-sh.uv`. |
| `rc` says the lock file is out of date | Run `rc-kit upgrade <name>`: the RC's `uv.lock` comes from the kit. |
| A codex role reads nothing on Windows | Codex's Windows sandbox blocks reading. Run codex roles from WSL, or move them to Claude: `./rc roles set <role> --provider claude --model sonnet`. |
