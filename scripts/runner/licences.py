"""Licence verdicts for profiles: a company profile may use only permissive licences, a personal profile any.

The runner, never an agent, classifies a licence from its SPDX id against templates/licences.json, so a card's licence
line is a lookup, not an opinion. An id that cannot be read or is in no class is unknown, and unknown is flagged.
See docs/decisions/0015-profiles.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import rc

UNKNOWN = "unknown"
NO_LICENCE = {"", "noassertion", "none", "other", "unlicensed"}


def table(root: Path) -> dict[str, Any]:
    return json.loads((rc.instance(root) / "templates" / "licences.json").read_text(encoding="utf-8"))


def normalized(spdx: str) -> str:
    return re.sub(r"-(only|or-later)$|\+$", "", spdx.strip()).lower()


def classify(root: Path, spdx: str | None) -> str:
    key = normalized(spdx or "")
    if key in NO_LICENCE:
        return UNKNOWN
    for name, members in table(root)["classes"].items():
        if key in {normalized(member) for member in members}:
            return name
    return UNKNOWN


def verdict(root: Path, spdx: str | None, profile_type: str) -> dict[str, Any]:
    """Whether a profile of this type may use something under this licence, and why not when it may not."""
    kind = classify(root, spdx)
    usable = kind == "permissive" if profile_type == "company" else True
    reason = "" if usable else table(root)["reasons"].get(kind, "")
    return {"spdx": spdx or None, "class": kind, "usable": usable, "reason": reason}
