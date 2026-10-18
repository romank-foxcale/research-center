"""The Research Center's command line: rc <command> [arguments].

Run through a launcher - rc.cmd or rc.ps1 on Windows, ./rc elsewhere - which starts it with uv in this RC's locked
environment (pyproject.toml, uv.lock), so the same command works on Windows, macOS, Linux and WSL with nothing else
installed (docs/decisions/0012-windows-native-uv.md).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"

USAGE = """Usage: rc [-p <profile>] <command> [arguments]

Profiles: ingest, research, report, tags, scout and watch work on one profile (profiles/<id>/), chosen with -p <id>, else RC_PROFILE,
else defaultProfile in research-center.json, else the only one there is. Everything else is the whole instance.

Commands:
  doctor         Check Python, git, gh and the provider logins
  check          Run every validator and test suite (the gate before a change is finished)
  validate       Validate the docs/ knowledge graph and the research center contract
  agents <sync|check>  Mirror .agents/skills into .claude/skills and the rule hooks
  bootstrap install [dir]  Materialize a new instance from this template (default: here)
  bootstrap validate       Validate the research center contract
  upgrade <instance> [--reset-roles]  From the template: bring an instance's template-owned files up to date
  ingest add <folder|git|url|notion|gdrive> <locator...> [--id] [--include] [--exclude] [--note]
  ingest list | remove <id>
  ingest run [id...] [--budget N] [--profile|--no-profile]  Fetch, digest, profile
  research new <topic> --title "..." | accept <topic> | list | show <topic>
  research run <topic> [--from plan|search|screen|collect|analyze|critique|judge|apply|report] [--budget N]
  research refresh <topic> | refresh --due [--budget N]  Re-search a living topic; write research/<topic>/delta/<date>.md
  research pause|resume|retire <topic>
  report [<topic>] [--output P]  A topic as one HTML page, or without a topic the dashboard and every topic's
                 page (.rc-local/reports/index.html)
  report [<topic>] --manifest | --shared-at <url>  What a share publishes; record the link it was shared at
  home [--manifest | --shared-at <url>]  The main screen: every profile's tags and technology cards, one page per card
  sources list | search <adapter> <query> [--filter k=v] [--since D] | related <adapter> <id> --direction backward|forward
  sources packs | enable <pack> | disable <pack> | new <adapter> --family F --evidence-type T | test [<adapter>]
  watch [run]    Follow an ingest or research run live: steps, agent talk, stalls, result
  settings [show]  Settings as text: status, budgets, limits, agents and their models
  roles [list] | roles set <role> [--provider claude|codex] [--model M]
  plan <create|list|show|accept|archive|complete> ...  Plans for changing this RC itself
  profile new <id> --name "..." --type company|personal [--description "..."]  A profile: whom the RC scouts for
  profile list | show <id> | edit <id> [--name] [--type] [--description] | scope <id> | accept <id>
  tags list | add "<tag>" [--why "..."] | remove <tag> | rename <old> <new>  A profile's interest tags
  tags suggest | accept [<tag>...|--all] | reject [<tag>...|--all]  Tags proposed from the profile's material
  scout [run] [--no-discover]  Discovery, then triage, technology cards and their challenge (about scout.calls agent calls)
  scout discover [--since D] [--tag T]  What is new for the profile's tags on GitHub, arXiv and OpenAlex (no agent)
  scout cards | dismiss <card>  The profile's technology cards; close one for good
  trends init | [run] | discover | cards | dismiss <card> | tags ...  The shared trend feed, judged against every profile"""

# The gate: what `rc check` runs, in order. Each entry is a label and the script with its arguments.
CHECKS = [
    ("knowledge", ["validate-knowledge.py", "{root}"]),
    ("contract", ["validate-research-center.py", "{root}"]),
    ("agent configs", ["agent-configs.py", "{root}", "check"]),
    ("agent configs test", ["agent_configs_test.py"]),
    ("rule hooks test", ["rule_hooks_test.py"]),
    ("providers test", ["runner/providers_test.py"]),
    ("secrets test", ["ingest/secrets_test.py"]),
    ("extract test", ["ingest/extract_test.py"]),
    ("ingest test", ["ingest/ingest_test.py"]),
    ("research test", ["research/research_test.py"]),
    ("report test", ["report/report_test.py"]),
    ("home test", ["report/home_test.py"]),
    ("sources test", ["sources/sources_test.py"]),
    ("upgrade test", ["upgrade_instance_test.py"]),
    ("profiles test", ["profiles_test.py"]),
    ("tags test", ["tags_test.py"]),
    ("scout test", ["scout/scout_test.py"]),
    ("cards test", ["scout/cards_test.py"]),
    ("trends test", ["scout/trends_test.py"]),
]
# Commands that hand over to one script with the root and the remaining arguments.
SCRIPT_COMMANDS = {
    "ingest": "ingest/ingest.py", "research": "research/research.py", "sources": "sources/sources.py",
    "watch": "runner/events.py", "roles": "roles.py", "plan": "plans.py", "agents": "agent-configs.py",
    "home": "report/home.py", "profile": "profiles.py", "tags": "tags.py", "scout": "scout/scout.py", "report": "report/report.py",
}
# Commands whose data lives in a profile: they get its folder as their root (docs/decisions/0015-profiles.md).
DATA_COMMANDS = {"ingest", "research", "watch", "report", "tags", "scout"}
# The flag that picks a profile; -u and --use-case are the names from before profiles, kept for one release.
PROFILE_FLAGS = ("-p", "--profile", "-u", "--use-case")


def profiles() -> list[str]:
    return sorted(path.parent.name for path in (ROOT / "profiles").glob("*/profile.json"))


def data_root(selected: str | None) -> Path:
    """The folder a data command works on: the chosen profile, or the instance itself when it has none."""
    names = profiles()
    if (ROOT / "usecases").is_dir():
        raise SystemExit("error: this RC still has usecases/; run rc upgrade from the template to move them to profiles/")
    if not names:
        if selected:
            raise SystemExit(f"error: no profile {selected}; create one with rc profile new {selected} --name \"...\" --type company")
        return ROOT
    default = None
    settings = ROOT / "research-center.json"
    if settings.is_file():
        config = json.loads(settings.read_text(encoding="utf-8"))
        default = config.get("defaultProfile") or config.get("defaultUseCase")
    chosen = os.environ.get("RC_PROFILE") or os.environ.get("RC_USE_CASE")
    name = selected or chosen or default or (names[0] if len(names) == 1 else None)
    if not name:
        raise SystemExit(f"error: this RC has several profiles ({', '.join(names)}); choose one with rc -p <id> ...")
    if name not in names:
        raise SystemExit(f"error: no profile {name}; rc profile list shows them")
    return ROOT / "profiles" / name


def script(name: str, *args: str, quiet: bool = False) -> int:
    """Run scripts/<name> with this interpreter; -B keeps __pycache__ out of the tree."""
    stream = subprocess.DEVNULL if quiet else None
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / name), *args], stdout=stream).returncode


def check() -> int:
    failed = []
    for label, (name, *args) in CHECKS:
        if not (SCRIPTS / name).is_file():
            continue
        started = time.monotonic()
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / name), *(arg.format(root=ROOT) for arg in args)],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        seconds = time.monotonic() - started
        if result.returncode == 0:
            print(f"pass  {label} ({seconds:.1f}s)")
        else:
            failed.append(label)
            print(f"FAIL  {label} ({seconds:.1f}s)\n{(result.stdout + result.stderr).strip()[-4000:]}\n")
    print(f"\n{len(CHECKS) - len(failed)} of {len(CHECKS)} checks passed" if not failed else f"\nfailed: {', '.join(failed)}")
    return 1 if failed else 0


def doctor() -> int:
    print(f"python {sys.version.split()[0]} ({sys.executable})")
    for tool, args in (("git", ["--version"]), ("uv", ["--version"])):
        found = shutil.which(tool)
        version = subprocess.run([found, *args], capture_output=True, text=True).stdout.strip() if found else ""
        print(f"{tool}: {version or 'missing'}")
    gh = shutil.which("gh")
    logged_in = bool(gh) and subprocess.run([gh, "auth", "status"], capture_output=True).returncode == 0
    print("gh: logged in" if logged_in else "note: gh is missing or not logged in; ingest cannot check that the remote is private")
    return script("runner/providers.py", "status")


def main(argv: list[str]) -> int:
    selected = None
    if argv[:1] and argv[0] in PROFILE_FLAGS:
        if len(argv) < 2:
            print("error: -p needs a profile id", file=sys.stderr)
            return 2
        selected, argv = argv[1], argv[2:]
    command, args = (argv[0], argv[1:]) if argv else ("help", [])
    if command in ("help", "-h", "--help"):
        print(USAGE)
        return 0
    if command == "check":
        return check()
    if command == "doctor":
        return doctor()
    if command == "validate":
        return script("validate-knowledge.py", str(ROOT)) or script("validate-research-center.py", str(ROOT))
    if command == "settings":
        return script("roles.py", str(ROOT), "show")
    if command == "bootstrap":
        sub = args[0] if args else ""
        if sub == "install":
            return script("materialize-template.py", args[1] if len(args) > 1 else ".")
        if sub == "validate":
            return script("validate-research-center.py", str(ROOT))
        print("usage: rc bootstrap <install [dir]|validate>", file=sys.stderr)
        return 2
    if command == "upgrade":
        return script("upgrade-instance.py", str(ROOT), *args)
    if command == "research" and args[:2] == ["refresh", "--due"] and not selected and len(profiles()) > 1:
        # Every profile's due topics; one failing does not stop the others.
        codes = [script(SCRIPT_COMMANDS["research"], str(ROOT / "profiles" / name), *args) for name in profiles()]
        return max(codes)
    if command == "trends":
        # The shared trend feed: trends/ is scouted like a profile (docs/decisions/0016-scouting.md).
        if args[:1] == ["tags"]:
            return script(SCRIPT_COMMANDS["tags"], str(ROOT / "trends"), *args[1:])
        return script(SCRIPT_COMMANDS["scout"], str(ROOT / "trends"), *(args or ["run"]))
    if command in SCRIPT_COMMANDS:
        if command == "agents" and not args:
            args = ["check"]
        root = data_root(selected) if command in DATA_COMMANDS else ROOT
        return script(SCRIPT_COMMANDS[command], str(root), *args)
    print(f"error: unknown command: {command}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    # Child scripts read and print agent output in UTF-8 whatever the console's code page is.
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main(sys.argv[1:]))
