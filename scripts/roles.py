#!/usr/bin/env python3
"""./rc roles: list the agent roles and the pipeline slots they fill, or change a role's provider or model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "runner"))
import providers  # noqa: E402


def roles_dir(root: Path) -> Path:
    return root / "catalog" / "agents" if (root / "research-center.json").is_file() else root / "templates" / "agents"


def slots(root: Path) -> dict[str, list[str]]:
    path = root / "research-center.json"
    if not path.is_file():
        path = root / "templates" / "research-center.json"
    pipeline = json.loads(path.read_text(encoding="utf-8"))["pipeline"]
    used: dict[str, list[str]] = {}
    for slot, value in pipeline.items():
        for role in value if isinstance(value, list) else [value]:
            used.setdefault(role, []).append(slot)
    return used


def command_list(root: Path) -> None:
    used = slots(root)
    for path in sorted(roles_dir(root).glob("*.json")):
        role = json.loads(path.read_text(encoding="utf-8"))
        print(f"{role['id']:<20} {role['provider']:<7} {role['model']:<18} {role['access']:<15} {', '.join(used.get(role['id'], ['unused']))}")


def command_show(root: Path) -> None:
    """./rc settings: the RC's settings as text, like ./cc settings show (no panel yet)."""
    path = root / "research-center.json"
    config = json.loads((path if path.is_file() else root / "templates" / "research-center.json").read_text(encoding="utf-8"))
    print(f"Research Center {config.get('name')}  status {config.get('status', 'unknown')}"
          f"{'' if path.is_file() else '  (template)'}")
    print(f"\nBudgets   ingest {config['budget']['ingestCalls']} calls · research {config['budget']['researchCalls']} calls"
          f" · refresh {config['budget'].get('refreshCalls', 16)} calls")
    ingest = config["ingest"]
    print(f"Ingest    max file {ingest['maxFileBytes']} B · max source {ingest['maxSourceBytes']} B · chunk {ingest['chunkBytes']} B")
    print(f"Research  max {config['research']['maxSourcesPerResearcher']} sources per researcher")
    print(f"Remote    privateRemoteConfirmed {str(config.get('privateRemoteConfirmed', False)).lower()}")
    print("\nAgents")
    command_list(root)
    print("\nChange a role: ./rc roles set <role> --provider <claude|codex|cursor> --model <model>; "
          f"other settings: edit {path.name}")


def command_set(root: Path, args: argparse.Namespace) -> None:
    path = roles_dir(root) / f"{args.id}.json"
    if not path.is_file():
        raise ValueError(f"no such role: {args.id}")
    role = json.loads(path.read_text(encoding="utf-8"))
    if args.provider:
        role["provider"] = args.provider
    if args.model:
        role["model"] = args.model
    try:
        providers.command(role, root, root / "last.txt")  # the same access rules the runner enforces
    except providers.ProviderError as error:
        raise ValueError(str(error)) from error
    available = providers.models(role["provider"])
    if available and role["model"] not in available:
        print(f"warning: {role['model']} is not among {role['provider']}'s listed models: {', '.join(available[:12])}", file=sys.stderr)
    path.write_text(json.dumps(role, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"{args.id}: {role['provider']} {role['model']} ({role['access']})")


def main() -> int:
    parser = argparse.ArgumentParser(prog="./rc roles")
    parser.add_argument("root", type=Path)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("list")
    commands.add_parser("show")
    setter = commands.add_parser("set")
    setter.add_argument("id")
    setter.add_argument("--provider", choices=providers.PROVIDERS)
    setter.add_argument("--model")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "set":
            command_set(root, args)
        elif args.command == "show":
            command_show(root)
        else:
            command_list(root)
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
