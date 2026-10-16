"""rc-kit: create, list, open, check and upgrade Research Centers from this kit (a clone of the template).

Installed by install/windows/install.ps1 or install/install.sh, and run through the rc-kit.cmd or rc-kit launcher
with uv in the kit's locked environment, so it works the same on Windows, macOS, Linux and WSL.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
PROJECTS = Path(os.environ.get("RC_PROJECTS_ROOT") or os.environ.get("CC_PROJECTS_ROOT") or Path.home() / "Projects")
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
TOOLS = ("code", "cursor", "claude", "codex", "opencode")

USAGE = f"""Usage: rc-kit <command> [arguments]

Commands:
  new <name>            Create {PROJECTS / '<name>_RC'} and prepare it for your AI tool
  list                  List Research Centers under {PROJECTS}
  open <name> <tool>    Open an RC in {', '.join(TOOLS)}
  upgrade <name> [--reset-roles]  Bring an RC's scripts, skills and templates up to this kit
  doctor                Check prerequisites, provider logins and AI tools
  update                Update the kit itself (then upgrade each RC you want on the new version)

Projects root: {PROJECTS} (set RC_PROJECTS_ROOT to change it)"""


def rc_dir(name: str) -> Path:
    name = name.removesuffix("_RC")
    if not NAME.fullmatch(name):
        raise SystemExit(f"error: name must use lowercase letters, digits and dashes: {name}")
    return PROJECTS / f"{name}_RC"


def run(*argv: str, cwd: Path | None = None) -> int:
    return subprocess.run([shutil.which(argv[0]) or argv[0], *argv[1:]], cwd=cwd).returncode


def command_new(name: str) -> int:
    target = rc_dir(name)
    if target.exists() and any(target.iterdir()):
        print(f"error: {target} already exists and is not empty.\n"
              f'To migrate an existing research setup, see "Migrating an existing research setup" in {KIT / "GUIDE.md"}', file=sys.stderr)
        return 1
    PROJECTS.mkdir(parents=True, exist_ok=True)
    code = subprocess.run([sys.executable, "-B", str(KIT / "scripts" / "materialize-template.py"), str(target)]).returncode
    if code:
        return code
    run("git", "-C", str(target), "add", "-A")
    launcher = "rc" if os.name == "nt" else "./rc"
    print(f"\nCreated {target}\n\nIt will hold the text of everything you ingest: give it a PRIVATE remote before ingesting.\n\n"
          f"Next: open it in your AI tool and start the setup interview.\n"
          f"  VS Code:   rc-kit open {target.name.removesuffix('_RC')} code\n"
          f"  Claude:    rc-kit open {target.name.removesuffix('_RC')} claude\n"
          f"  Claude desktop: open the folder {target}\n\n"
          f"First prompt:  Set up this Research Center. Use the grill-rc-bootstrap skill.\n"
          f"Check it any time with: {launcher} check")
    return 0


def command_list() -> int:
    found = False
    for directory in sorted(PROJECTS.glob("*_RC")):
        settings = directory / "research-center.json"
        if settings.is_file():
            try:
                status = json.loads(settings.read_text(encoding="utf-8")).get("status", "unknown")
            except (OSError, ValueError):
                status = "unreadable settings"
            print(f"{directory.name:<40} {status}{'' if (directory / 'rc.py').is_file() else '  (old version: rc-kit upgrade)'}")
            found = True
    if not found:
        print(f"No Research Centers in {PROJECTS} yet. Create one with: rc-kit new <name>")
    return 0


def command_open(name: str, tool: str) -> int:
    target = rc_dir(name)
    if not (target / "research-center.json").is_file():
        print(f"error: no Research Center at {target}", file=sys.stderr)
        return 1
    if tool not in TOOLS:
        print(f"error: unknown tool {tool}; one of {', '.join(TOOLS)}", file=sys.stderr)
        return 2
    if not shutil.which(tool):
        print(f'error: "{tool}" is not installed or not on PATH; see GUIDE.md', file=sys.stderr)
        return 1
    return run(tool, str(target)) if tool in ("code", "cursor") else run(tool, cwd=target)


def command_upgrade(name: str, *flags: str) -> int:
    return subprocess.run([sys.executable, "-B", str(KIT / "scripts" / "upgrade-instance.py"), str(KIT), str(rc_dir(name)), *flags]).returncode


def command_doctor() -> int:
    failures = 0

    def report(ok: bool, text: str, required: bool = True) -> None:
        nonlocal failures
        print(f"  {'ok  ' if ok else ('FAIL' if required else 'warn')}  {text}")
        failures += (not ok) and required

    def version(tool: str, *args: str) -> str:
        result = subprocess.run([shutil.which(tool), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return (result.stdout or result.stderr).strip().splitlines()[0] if result.stdout or result.stderr else "?"

    print("System")
    report(True, f"{platform.system()} {platform.release()}, Python {platform.python_version()}")
    report(True, f"projects root: {PROJECTS}")
    print("\nRequired")
    for tool, args in (("git", ("--version",)), ("uv", ("--version",))):
        found = shutil.which(tool)
        report(bool(found), f"{tool}: {version(tool, *args) if found else 'missing; re-run the installer'}")
    gh = shutil.which("gh")
    logged = bool(gh) and subprocess.run([gh, "auth", "status"], capture_output=True).returncode == 0
    report(logged, "gh logged in (ingest checks that your RC's remote is private)" if logged
           else "gh is missing or not logged in; run: gh auth login")
    sys.path.insert(0, str(KIT / "scripts" / "runner"))
    import providers

    print("\nResearch providers (claude is required; every default role runs on it)")
    available, detail = providers.login_status("claude")
    report(available, f"claude: {detail}")
    available, detail = providers.login_status("codex")
    note = " (its read-only sandbox cannot read files on native Windows; codex roles need macOS, Linux or WSL)" if os.name == "nt" else ""
    report(available, f"codex: {detail}{note}", required=False)
    print("\nOptional")
    for tool in ("code", "cursor", "opencode"):
        report(bool(shutil.which(tool)), f"{tool} command {'found' if shutil.which(tool) else 'not on PATH'}", required=False)
    commit = subprocess.run(["git", "-C", str(KIT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    print(f"\nKit: {KIT} ({commit or 'not a git clone'})")
    print(f"{failures} required check(s) failed." if failures else "All required checks passed.")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    command, args = (argv[0], argv[1:]) if argv else ("help", [])
    if command in ("help", "-h", "--help"):
        print(USAGE)
        return 0
    if command == "new" and len(args) == 1:
        return command_new(args[0])
    if command == "list":
        return command_list()
    if command == "open" and len(args) == 2:
        return command_open(*args)
    if command == "upgrade" and args:
        return command_upgrade(*args)
    if command == "doctor":
        return command_doctor()
    if command == "update":
        code = run("git", "-C", str(KIT), "pull", "--ff-only")
        print("Kit updated. Research Centers are separate repos: upgrade each one with rc-kit upgrade <name>." if code == 0 else "")
        return code
    print(f"error: unknown command or arguments: {' '.join(argv)}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main(sys.argv[1:]))
