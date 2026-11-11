#!/usr/bin/env python3
"""rc home [--manifest | --shared-at <url>]: the main screen - every profile's tags and technology cards, one page
per card, and each profile's research - as self-contained HTML in one folder that can be shared whole.

.rc-local/reports/home/
  index.html                      the main screen: trends (when there are any), then each profile
  <profile>/<card>.html           a technology card: plain words first, then the engineers' part
  <profile>/research/index.html   the profile's research dashboard, with its topic pages beside it

Pages are computed from the committed cards and outputs, never written by an agent, with the escaping, redaction
and theming of report.py (docs/decisions/0014-report-pages.md). Cards are grouped by verdict; dismissed cards are
left out and counted. A card whose licence the profile cannot use says so on the main screen as well.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import report  # noqa: E402
from report import badge, esc, link, rc, write_page  # noqa: E402

VERDICT_ORDER = ("worth testing", "watch", "not a fit")
VERDICT_HELP = {
    "worth testing": "A plausible gain within the profile's constraints, with a cheap experiment to run.",
    "watch": "Relevant, but immature, unproven on the profile's data, or blocked by something that may change.",
    "not a fit": "Does something else, breaks a hard constraint, or what the profile has already does it.",
}
STYLE = """
.verdict-worth-testing{color:var(--ok)}.verdict-watch{color:var(--weak)}.verdict-not-a-fit{color:var(--bad)}
.card.v-worth-testing{border-left-color:var(--ok)}.card.v-watch{border-left-color:var(--weak)}.card.v-not-a-fit{border-left-color:var(--bad)}
.flag{display:inline-block;font-size:.78rem;padding:1px 8px;border-radius:999px;background:var(--i);color:var(--ink)}
.flag.soft{background:var(--n)}
.profile-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 12px}.profile-head h2{margin:0}
.group{margin:18px 0 6px;font-size:1rem}.group .hint{font-weight:400}
.banner{padding:10px 14px;border-radius:10px;background:var(--i);margin:12px 0}.banner.ok{background:var(--c)}
.plan{border-collapse:collapse}.plan th{width:9em;color:var(--muted);font-weight:500}
.quote{color:var(--muted)}
"""


def profiles(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path.parent, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((root / "profiles").glob("*/profile.json"))
    ]


def cards(profile_root: Path) -> list[dict[str, Any]]:
    found = [json.loads(path.read_text(encoding="utf-8")) for path in (profile_root / "scout" / "cards").glob("*.json")]
    return sorted(found, key=lambda card: (card["date"], card["id"]), reverse=True)


def flags(card: dict[str, Any]) -> str:
    out = []
    licence = card.get("licence")
    if licence and not licence["usable"]:
        out.append(
            f'<span class="flag" title="{esc(licence["reason"])}">licence {esc(licence["spdx"] or "none found")}: not usable</span>'
        )
    review = card.get("review") or {}
    if card.get("verdictBy") == "sceptic":
        out.append(
            f'<span class="flag" title="{esc("; ".join(review.get("issues", [])))}">verdict changed by the sceptic</span>'
        )
    elif review.get("verdict") == "overstated":
        out.append(
            f'<span class="flag soft" title="{esc("; ".join(review.get("issues", [])))}">sceptic: partly overstated</span>'
        )
    return " ".join(out)


def affects_text(card: dict[str, Any]) -> str:
    """For a trend card: the profiles it may affect, with the component and how."""
    return (
        "; ".join(f"{entry['profile']} ({entry['component']}): {entry['how']}" for entry in card.get("affects", []))
        or "no profile"
    )


def card_tile(card: dict[str, Any], href: str) -> str:
    kind = card.get("kind", "")
    return (
        f'<article class="card v-{esc(card["verdict"].replace(" ", "-"))}"><div class="card-head">'
        f'<h3><a href="{esc(href)}">{esc(card["title"])}</a></h3>{badge("verdict", card["verdict"])}</div>'
        f"<p>{esc(card['headline'])}</p>"
        f'<p class="hint">{esc(kind)} · {esc(card["date"])} · {esc(", ".join(card.get("tags", [])))}</p>'
        + (f'<p class="hint">May affect: {esc(affects_text(card))}</p>' if "affects" in card else "")
        + (f"<p>{flags(card)}</p>" if flags(card) else "")
        + "</article>"
    )


def profile_section(profile_root: Path, meta: dict[str, Any]) -> str:
    pid = meta["id"]
    every = cards(profile_root)
    open_cards = [card for card in every if card.get("status", "open") != "dismissed"]
    dismissed = len(every) - len(open_cards)
    tags = "".join(f'<span class="badge tag">{esc(name)}</span>' for name in report.tag_names(meta) if name)
    groups = []
    for verdict in VERDICT_ORDER:
        members = [card for card in open_cards if card["verdict"] == verdict]
        if members:
            tiles = "".join(card_tile(card, f"{pid}/{card['id']}.html") for card in members)
            groups.append(
                f'<h3 class="group">{badge("verdict", verdict)} <span class="hint">{esc(VERDICT_HELP[verdict])}</span></h3>'
                f'<div class="cards">{tiles}</div>'
            )
    body = "".join(groups) or '<p class="missing">No technology cards yet: run rc -p ' + esc(pid) + " scout.</p>"
    research = (
        f'<p><a href="{esc(pid)}/research/index.html">Research topics ({len(report.topic_ids(profile_root))})</a></p>'
        if report.topic_ids(profile_root)
        else ""
    )
    state = profile_root / "scout" / "state.json"
    last = json.loads(state.read_text(encoding="utf-8")).get("lastDiscovery") if state.is_file() else None
    facts = (
        [f"{len(open_cards)} cards"]
        + ([f"{dismissed} dismissed"] if dismissed else [])
        + ([f"last scouted {last}"] if last else [])
    )
    return (
        f'<section id="{esc(pid)}"><div class="profile-head"><h2>{esc(meta.get("name", pid))}</h2>'
        f'{badge("status", meta.get("type", ""))}<span class="hint">{esc(" · ".join(facts))}</span></div>'
        + (f"<p>{esc(meta['description'])}</p>" if meta.get("description") else "")
        + (f'<div class="legend tags">{tags}</div>' if tags else "")
        + body
        + research
        + "</section>"
    )


def trends_section(root: Path) -> str:
    """The shared trend feed (scouting plan WP5); until it exists, the main screen says so in one line."""
    found = (
        [card for card in cards(root / "trends") if card.get("status", "open") != "dismissed"]
        if (root / "trends").is_dir()
        else []
    )
    if not found:
        return ""
    found.sort(key=lambda card: (VERDICT_ORDER.index(card["verdict"]), card["title"]))
    tiles = "".join(card_tile(card, f"trends/{card['id']}.html") for card in found)
    return (
        f'<section id="trends"><h2>Trends across profiles</h2><p class="hint">Releases and research that may change how '
        f'any profile works; each card names the profiles it may affect.</p><div class="cards">{tiles}</div></section>'
    )


def render_home(root: Path, fragment: bool = False) -> str:
    entries = profiles(root)
    name = rc.settings(root).get("name", "Research Center")
    total = sum(len([card for card in cards(path) if card.get("status", "open") != "dismissed"]) for path, _ in entries)
    nav = (
        '<nav class="toc">'
        + "".join(f'<a href="#{esc(meta["id"])}">{esc(meta.get("name", meta["id"]))}</a>' for _, meta in entries)
        + "</nav>"
    )
    sections = (
        "".join(profile_section(path, meta) for path, meta in entries)
        or '<section><p class="missing">No profiles yet: rc profile new &lt;id&gt; --name "..." --type company|personal</p></section>'
    )
    return report.page(
        f"{name} scouting",
        f'<style>{STYLE}</style><header class="top"><p class="crumbs">Research Center</p>'
        f'<h1>Technology scouting</h1><p class="meta">{esc(name)} · {len(entries)} profile{"s" if len(entries) != 1 else ""}'
        f" · {total} open cards</p></header>{nav}{trends_section(root)}{sections}"
        "<footer>Cards are computed from stored evidence and reviewed by a sceptic; every claim quotes its source.</footer>",
        script=False,
        fragment=fragment,
    )


def render_card(card: dict[str, Any], profile: dict[str, Any], up: str = "../index.html") -> str:
    leaders, engineers, plan = card["leaders"], card["engineers"], card["engineers"]["evaluation"]
    licence = card.get("licence")
    review = card.get("review") or {}
    banner = ""
    if licence:
        banner = (
            f'<p class="banner ok"><b>Licence:</b> {esc(licence["spdx"] or "none found")} ({esc(licence["class"])}), usable by this profile.</p>'
            if licence["usable"]
            else f'<p class="banner"><b>Licence:</b> {esc(licence["spdx"] or "none found")} ({esc(licence["class"])}), '
            f"<b>not usable for a {esc(profile.get('type', ''))} profile:</b> {esc(licence['reason'])}.</p>"
        )
    changed = (
        f'<p class="banner">The sceptic changed the verdict from "{esc(card["evaluatorVerdict"])}" to "{esc(card["verdict"])}".</p>'
        if card.get("verdictBy") == "sceptic"
        else ""
    )
    plain = "".join(
        f"<dt>{label}</dt><dd>{esc(leaders[key])}</dd>"
        for key, label in (
            ("whatItIs", "What it is"),
            ("whatItCouldDo", "What it could do for us"),
            ("wherePlugsIn", "Where it would plug in"),
            ("why", "Why this verdict"),
        )
    )
    lists = "".join(
        f"<h3>{title}</h3><ul>" + "".join(f"<li>{esc(entry)}</li>" for entry in engineers[key]) + "</ul>"
        for key, title in (("pros", "Pros"), ("cons", "Cons"), ("risks", "Risks"))
    )
    rows = "".join(
        f'<tr><th scope="row">{label}</th><td>{esc(plan[key])}</td></tr>'
        for key, label in (
            ("experiment", "Experiment"),
            ("metric", "Metric"),
            ("passBar", "Pass bar"),
            ("effort", "Effort"),
        )
    )
    sceptic = (
        (
            f'<section id="sceptic"><h2>Sceptic</h2><p>Review: {badge("verdict", review["verdict"])}</p>'
            + (
                "<ul>" + "".join(f"<li>{esc(issue)}</li>" for issue in review.get("issues", [])) + "</ul>"
                if review.get("issues")
                else ""
            )
            + "</section>"
        )
        if review
        else ""
    )
    claims = "".join(
        f'<li>{esc(claim["text"])} <span class="quote">"{esc(claim["quote"])}"</span></li>' for claim in card["claims"]
    )
    body = (
        f'<header class="top"><p class="crumbs"><a href="{esc(up)}">&larr; Main screen</a> · {esc(profile.get("name", ""))}</p>'
        f'<h1>{esc(card["title"])}</h1><p class="meta">{badge("verdict", card["verdict"])} {esc(card.get("kind", ""))} · found {esc(card["date"])}'
        f" for {esc(', '.join(card.get('tags', [])))} · {link(card['url'], 'source')}</p></header>"
        f'<section class="lead plain"><h2>{esc(card["headline"])}</h2>{banner}{changed}<dl>{plain}</dl></section>'
        f'<section id="engineers"><h2>For engineers</h2><h3>How it works</h3><p>{esc(engineers["howItWorks"])}</p>'
        f"<dl><dt>Component</dt><dd>{esc(engineers['component'])}</dd><dt>Today</dt><dd>{esc(engineers['componentToday'])}</dd>"
        f"<dt>Replaces</dt><dd>{esc(engineers['replaces'])}</dd><dt>Alternatives</dt><dd>{esc(engineers['alternatives'])}</dd>"
        f"<dt>Maturity</dt><dd>{esc(engineers['maturity'])}</dd></dl>{lists}"
        f'<h3>How to evaluate it</h3><div class="scroll"><table class="plan">{rows}</table></div></section>'
        f'{sceptic}<section id="evidence"><h2>Evidence</h2><p class="hint">Quotes checked word for word against the stored page '
        f"({esc(card['evidence'])}). The fit rests on {esc(', '.join(card.get('profileBasis', [])))}.</p><ul>{claims}</ul></section>"
        "<footer>Technology card computed from stored evidence; the verdict was reviewed by a sceptic.</footer>"
    )
    return report.page(card["title"], f"<style>{STYLE}</style>{body}", script=False)


def folder(root: Path) -> Path:
    return root / ".rc-local" / "reports" / "home"


def command_home(root: Path) -> tuple[Path, dict[str, str]]:
    """Write the main screen and every page beside it; return the main page and the pages beside it by path."""
    out = folder(root)
    beside: dict[str, str] = {}
    trends = root / "trends"
    if (trends / "profile.json").is_file():
        meta = json.loads((trends / "profile.json").read_text(encoding="utf-8"))
        for card in cards(trends):
            if card.get("status", "open") != "dismissed":
                path = write_page(out / "trends" / f"{card['id']}.html", render_card(card, meta))
                beside[f"trends/{card['id']}.html"] = str(path)
    for profile_root, meta in profiles(root):
        pid = meta["id"]
        for card in cards(profile_root):
            if card.get("status", "open") != "dismissed":
                path = write_page(out / pid / f"{card['id']}.html", render_card(card, meta))
                beside[f"{pid}/{card['id']}.html"] = str(path)
        topics = report.topic_ids(profile_root)
        if topics:
            research = out / pid / "research"
            for topic in topics:
                path = write_page(research / f"{topic}.html", report.render_topic(profile_root, topic, dashboard=True))
                beside[f"{pid}/research/{topic}.html"] = str(path)
            path = write_page(research / "index.html", report.render_dashboard(profile_root, up="../../index.html"))
            beside[f"{pid}/research/index.html"] = str(path)
    return write_page(out / "index.html", render_home(root)), beside


def main() -> int:
    parser = argparse.ArgumentParser(prog="rc home", description="The main screen: every profile's cards and research")
    parser.add_argument("root", type=Path)
    parser.add_argument("--manifest", action="store_true", help="after writing, print what a share publishes, as JSON")
    parser.add_argument("--shared-at", metavar="URL", help="record the artifact link the main screen was shared at")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.shared_at:
            report.remember_share(folder(root), "index", args.shared_at)
            print(f"recorded: the main screen is shared at {args.shared_at}")
            return 0
        page, beside = command_home(root)
        if args.manifest:
            shared = write_page(folder(root) / "share" / "index.html", render_home(root, fragment=True))
            print(
                json.dumps(
                    {
                        "page": str(shared),
                        "files": beside,
                        "title": f"{rc.settings(root).get('name', 'Research Center')} scouting",
                        "sharedAt": report.shares(folder(root)).get("index"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
    except (rc.RcError, OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote {page} and {len(beside)} pages beside it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
