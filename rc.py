"""The Research Center's command line: rc <command> [arguments].

Run through a launcher - rc.cmd or rc.ps1 on Windows, ./rc elsewhere - which starts it with uv in this RC's locked
environment (pyproject.toml, uv.lock), so the same command works on Windows, macOS, Linux and WSL with nothing else
installed (docs/decisions/0012-windows-native-uv.md).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"

USAGE = """Usage: rc <command> [arguments]

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
  sources list | search <adapter> <query> [--filter k=v] [--since D] | related <adapter> <id> --direction backward|forward
  sources packs | enable <pack> | disable <pack> | new <adapter> --family F --evidence-type T | test [<adapter>]
  watch [run]    Follow an ingest or research run live: steps, agent talk, stalls, result
  settings [show]  Settings as text: status, budgets, limits, agents and their models
  roles [list] | roles set <role> [--provider claude|codex] [--model M]
  plan <create|list|show|accept|archive|complete> ...  Plans for changing this RC itself"""

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
    ("sources test", ["sources/sources_test.py"]),
    ("upgrade test", ["upgrade_instance_test.py"]),
]
# Commands that hand over to one script with the root and the remaining arguments.
SCRIPT_COMMANDS = {
    "ingest": "ingest/ingest.py", "research": "research/research.py", "sources": "sources/sources.py",
    "watch": "runner/events.py", "roles": "roles.py", "plan": "plans.py", "agents": "agent-configs.py",
}


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
    if command in SCRIPT_COMMANDS:
        if command == "agents" and not args:
            args = ["check"]
        return script(SCRIPT_COMMANDS[command], str(ROOT), *args)
    print(f"error: unknown command: {command}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    # Child scripts read and print agent output in UTF-8 whatever the console's code page is.
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main(sys.argv[1:]))
