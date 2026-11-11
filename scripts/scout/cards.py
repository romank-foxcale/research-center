"""Triage, technology cards and their challenge: what turns a profile's candidates into a few readable verdicts.

triage     one call: the scout-triage role ranks the open candidates against the profile and picks the few worth
           a card (scout.cardsPerRun); the rest are marked passed in the seen-list, with the run that passed them
evidence   the runner fetches what each pick's card may rely on - a repository's README, a paper's abstract page -
           and stores it under scout/evidence/, secrets redacted; for repositories it also states the licence
           verdict (scripts/runner/licences.py), which no agent sets
card       one call per pick: the scout-evaluator writes the card - for leaders, what it is, what it could do for
           the profile, where it plugs in, the verdict and why; for engineers, how it works, the component it
           touches and what that does today, alternatives, pros, cons, risks, maturity and an evaluation plan.
           Claims about the find quote the stored evidence and are checked like research quotes
challenge  one call: the scout-sceptic tests every card's fit against the profile and the evidence. A card it
           finds wrong takes the sceptic's verdict, and the card says so

"Not a fit" is a full result: the card names the component and why. Cards are scout/cards/<id>.json, rendered to
.md by the runner. See docs/decisions/0016-scouting.md.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [
    str(HERE.parent / "runner"),
    str(HERE.parent / "sources"),
    str(HERE.parent / "research"),
    str(HERE.parent),
]
import kit  # noqa: E402
import research  # noqa: E402  (quote checking)

import rc  # noqa: E402

VERDICTS = ("worth testing", "watch", "not a fit")
REVIEWS = ("holds", "overstated", "wrong")
EFFORTS = ("S", "M", "L")
MIN_EVIDENCE_CLAIMS = 2
TRIAGE_LIMIT = 300  # candidates shown to triage in one call, most-tagged and most-starred first
EVIDENCE_BYTES = 60_000
LEADERS = ("whatItIs", "whatItCouldDo", "wherePlugsIn", "why")
ENGINEERS = ("howItWorks", "component", "componentToday", "replaces", "alternatives", "maturity")


def slug(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:70]


def open_candidates(root: Path) -> list[dict[str, Any]]:
    """Every candidate still marked candidate in the seen-list, newest run first, most tags then stars first."""
    directory = root / "scout"
    seen = (
        json.loads((directory / "seen.json").read_text(encoding="utf-8")) if (directory / "seen.json").is_file() else {}
    )
    found: dict[str, dict[str, Any]] = {}
    for path in sorted((directory / "candidates").glob("*.json"), reverse=True):
        for item in json.loads(path.read_text(encoding="utf-8"))["candidates"]:
            if seen.get(item["key"], {}).get("status") == "candidate" and item["key"] not in found:
                found[item["key"]] = item
    ordered = sorted(found.values(), key=lambda item: (-len(item["tags"]), -item.get("stars", 0), item["title"]))
    return ordered[:TRIAGE_LIMIT]


def mark(root: Path, keys: list[str], status: str, stamp: str, note: dict[str, str] | None = None) -> None:
    path = root / "scout" / "seen.json"
    seen = json.loads(path.read_text(encoding="utf-8"))
    for key in keys:
        if key in seen:
            seen[key].update({"status": status, "run": stamp, **({"note": note[key]} if note and key in note else {})})
    rc.write_json(path, seen)


def line(index: int, item: dict[str, Any]) -> str:
    facts = [item["kind"], f"tags: {', '.join(item['tags'])}", item.get("date") or "undated"]
    if item["kind"] == "repository":
        facts += [f"{item.get('stars', 0)} stars", f"licence {item['licence']['class']}", item.get("language") or ""]
    text = " ".join((item.get("abstract") or "").split())[:280]
    return f"K{index} | {item['title']} | {' | '.join(fact for fact in facts if fact)} | {text}"


TRENDS = "trends"  # the instance's shared trend feed: scouted like a profile, judged against every profile


def is_trends(root: Path) -> bool:
    return root.name == TRENDS and (root.parent / "profiles").is_dir()


def trend_profiles(root: Path) -> list[str]:
    """The profiles a trend card is judged against, by id."""
    return sorted(path.parent.name for path in (root.parent / "profiles").glob("*/profile.json"))


def profile_reading(root: Path) -> str:
    files = ["profile.json"] + (["scope.md"] if (root / "scope.md").is_file() else [])
    if (root / "knowledge" / "profile" / "index.md").is_file():
        files.append("knowledge/profile/index.md and the notes it links")
    if is_trends(root):
        for pid in trend_profiles(root):
            files.append(
                f"../profiles/{pid}/profile.json"
                + (
                    f" and ../profiles/{pid}/scope.md"
                    if (root.parent / "profiles" / pid / "scope.md").is_file()
                    else ""
                )
            )
    return ", ".join(files)


# Triage ---------------------------------------------------------------------------------------------------


def triage(
    session: rc.Session, root: Path, candidates: list[dict[str, Any]], picks: int, role: str
) -> list[dict[str, Any]]:
    numbered = {f"K{index}": item for index, item in enumerate(candidates, 1)}
    meta = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    body = (
        f"# Task\n\nTriage {len(candidates)} new finds for the profile {meta.get('name')} ({meta.get('type')}). "
        + (
            "This is the shared trends feed: judge every find against all the profiles listed. "
            if is_trends(root)
            else ""
        )
        + f"Read {profile_reading(root)} first. Pick at most {picks} that most deserve a technology card.\n\n"
        "# Candidates, one per line: id | title | kind, tags, date, stars, licence, language | summary\n\n"
        + "\n".join(line(index, item) for index, item in enumerate(candidates, 1))
        + "\n"
    )

    def check(reply: str) -> list[dict[str, Any]]:
        data = rc.extract_json(reply)
        if not isinstance(data, dict) or not isinstance(data.get("picks"), list):
            raise ValueError("reply with a JSON object whose picks is a list (it may be empty)")
        problems, chosen = [], []
        if len(data["picks"]) > picks:
            problems.append(f"pick at most {picks}")
        for pick in data["picks"]:
            if not isinstance(pick, dict) or pick.get("id") not in numbered:
                problems.append(f"{pick!r} does not name a candidate id like K3")
            elif not str(pick.get("why", "")).strip() or not str(pick.get("component", "")).strip():
                problems.append(f"{pick['id']} needs why and component")
            elif pick["id"] in {item["id"] for item in chosen}:
                problems.append(f"{pick['id']} is picked twice")
            else:
                chosen.append(
                    {
                        "id": pick["id"],
                        "why": " ".join(str(pick["why"]).split()),
                        "component": " ".join(str(pick["component"]).split()),
                    }
                )
        if problems:
            raise ValueError("; ".join(problems[:10]))
        return [{**numbered[pick["id"]], "triage": pick} for pick in chosen]

    return session.call_checked(role, body, "triage", check)


# Evidence -------------------------------------------------------------------------------------------------


def fetch_evidence(item: dict[str, Any]) -> str:
    """What a card may quote: a repository's README, or a paper's abstract page; the candidate's own summary when
    nothing more can be had."""
    match = re.match(r"https://github\.com/([^/]+/[^/#?]+)", item["url"])
    try:
        if item["kind"] == "repository" and match:
            headers = {"Accept": "application/vnd.github.raw"}
            if os.environ.get("GITHUB_TOKEN"):
                headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
            data, _ = kit.fetch(f"https://api.github.com/repos/{match.group(1)}/readme", interval=1.0, headers=headers)
            return data.decode("utf-8", errors="replace")[:EVIDENCE_BYTES]
        if "arxiv.org/abs/" in item["url"]:
            data, _ = kit.fetch(item["url"].replace("http://", "https://"), interval=3.0)
            return kit.strip_html(data.decode("utf-8", errors="replace"))[:EVIDENCE_BYTES]
    except kit.AdapterError:
        pass
    return item.get("abstract", "")


def store_evidence(root: Path, item: dict[str, Any]) -> str:
    """Store the evidence page and return its path relative to the profile."""
    facts = [f"URL: {item['url']}", f"Kind: {item['kind']}", f"Date: {item.get('date') or 'unknown'}"]
    if item["kind"] == "repository":
        facts += [
            f"Stars: {item.get('stars', 0)}",
            f"Language: {item.get('language') or 'unknown'}",
            f"Created: {item.get('created') or 'unknown'}",
            f"Archived: {item.get('archived', False)}",
            f"Licence: {item['licence']['spdx'] or 'none found'} ({item['licence']['class']})",
        ]
    text = fetch_evidence(item)
    relative = f"scout/evidence/{slug(item['key'])}.md"
    rc.write_text(
        root / relative,
        f"# {item['title']}\n\n" + "\n".join(f"- {fact}" for fact in facts) + f"\n\n## Text\n\n{text}\n",
    )
    return relative


# Cards ----------------------------------------------------------------------------------------------------


def card_problems(data: Any, evidence: str, root: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["reply with one JSON object: the card"]
    problems = []
    if data.get("verdict") not in VERDICTS:
        problems.append(f"verdict must be one of {', '.join(VERDICTS)}")
    if not str(data.get("headline", "")).strip():
        problems.append("headline is missing")
    leaders, engineers = data.get("leaders"), data.get("engineers")
    if not isinstance(leaders, dict) or not isinstance(engineers, dict):
        return [*problems, "leaders and engineers must be objects"]
    problems += [f"leaders.{name} is missing" for name in LEADERS if not str(leaders.get(name, "")).strip()]
    problems += [f"engineers.{name} is missing" for name in ENGINEERS if not str(engineers.get(name, "")).strip()]
    for name in ("pros", "cons", "risks"):
        if not isinstance(engineers.get(name), list) or not engineers[name]:
            problems.append(f"engineers.{name} must be a non-empty list")
    plan = engineers.get("evaluation")
    if not isinstance(plan, dict) or any(
        not str(plan.get(name, "")).strip() for name in ("experiment", "metric", "passBar")
    ):
        problems.append("engineers.evaluation needs experiment, metric and passBar")
    elif plan.get("effort") not in EFFORTS:
        problems.append(f"engineers.evaluation.effort must be one of {', '.join(EFFORTS)}")
    claims = data.get("claims")
    if not isinstance(claims, list):
        return [*problems, "claims must be a list"]
    verified = 0
    for claim in claims:
        if (
            not isinstance(claim, dict)
            or not str(claim.get("text", "")).strip()
            or not str(claim.get("quote", "")).strip()
        ):
            problems.append("every claim needs text and quote")
        elif research.quote_found(claim["quote"], evidence):
            verified += 1
        else:
            problems.append(f'the quote "{str(claim["quote"])[:60]}" is not in the evidence page, word for word')
    if verified < MIN_EVIDENCE_CLAIMS:
        problems.append(
            f"quote the evidence page at least {MIN_EVIDENCE_CLAIMS} times (at least {research.MIN_QUOTE_WORDS} words each)"
        )
    basis = data.get("profileBasis")
    if not isinstance(basis, list) or not basis:
        problems.append("profileBasis must list the profile files the fit rests on")
    else:
        problems += [
            f"profileBasis {path} is not a file of the profile"
            for path in basis
            if not (root / re.sub(r"#.*$", "", str(path))).is_file()
        ]
    if is_trends(root):
        known = trend_profiles(root)
        affects = data.get("affects")
        if not isinstance(affects, list):
            problems.append(
                "a trend card needs affects: the profiles it may affect, each with component and how (an empty list when none)"
            )
        else:
            for entry in affects:
                if not isinstance(entry, dict) or entry.get("profile") not in known:
                    problems.append(f"affects names {entry!r}; use one of the profiles {', '.join(known)}")
                elif not str(entry.get("component", "")).strip() or not str(entry.get("how", "")).strip():
                    problems.append(f"affects {entry['profile']}: needs component and how")
            if not affects and data.get("verdict") != "not a fit":
                problems.append("a trend that affects no profile is 'not a fit'")
    return problems


def evaluate(session: rc.Session, root: Path, item: dict[str, Any], evidence_path: str, role: str) -> dict[str, Any]:
    meta = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    licence = item.get("licence")
    licence_line = (
        f"Licence (set by the runner, not by you): {licence['spdx'] or 'none found'}, class {licence['class']}, "
        + (
            "usable by this profile."
            if licence["usable"]
            else f"NOT usable by this {meta.get('type')} profile: {licence['reason']}."
        )
        if licence
        else "Licence: not applicable (a paper or article)."
    )
    scope_line = (
        f"This is the shared trends feed: judge the find against every profile ({', '.join(trend_profiles(root))}), and "
        "fill affects with each profile it may affect, the component and how. It need not touch their products: a "
        "better way to build their software counts. "
        if is_trends(root)
        else f"for the profile {meta.get('name')} ({meta.get('type')}). "
    )
    body = (
        f"# Task\n\nWrite the technology card for one find, {scope_line}"
        f"Read {profile_reading(root)}, then the evidence page {evidence_path}.\n\n"
        f"Find: {item['title']} ({item['kind']}), {item['url']}\nFound by the tags: {', '.join(item['tags'])}\n"
        f"Triage said: {item['triage']['why']} (component: {item['triage']['component']})\n{licence_line}\n"
    )
    evidence = (root / evidence_path).read_text(encoding="utf-8")

    def check(reply: str) -> dict[str, Any]:
        data = rc.extract_json(reply)
        problems = card_problems(data, evidence, root)
        if problems:
            raise ValueError("; ".join(problems[:12]))
        return data

    return session.call_checked(role, body, f"card-{slug(item['key'])[:40]}", check)


def challenge(session: rc.Session, root: Path, cards: list[dict[str, Any]], role: str) -> dict[str, dict[str, Any]]:
    ids = {card["id"] for card in cards}
    body = (
        f"# Task\n\nChallenge {len(cards)} technology cards for the profile"
        + (" feed of shared trends, including each card's affects" if is_trends(root) else "")
        + f". Read {profile_reading(root)}. "
        "For each card, read its evidence page and test its verdict and fit claims.\n\n"
        + "\n\n".join(
            f"## Card {card['id']}\n\nEvidence page: {card['evidence']}\n\n```json\n"
            + json.dumps(
                {
                    key: card[key]
                    for key in ("title", "verdict", "headline", "leaders", "engineers", "affects")
                    if key in card
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n```"
            for card in cards
        )
        + "\n"
    )

    def check(reply: str) -> dict[str, dict[str, Any]]:
        data = rc.extract_json(reply)
        if not isinstance(data, dict) or not isinstance(data.get("reviews"), list):
            raise ValueError("reply with a JSON object whose reviews is a list")
        reviews, problems = {}, []
        for review in data["reviews"]:
            if not isinstance(review, dict) or review.get("card") not in ids:
                problems.append(f"{review!r} does not name a card")
                continue
            if review.get("verdict") not in REVIEWS:
                problems.append(f"{review['card']}: verdict must be one of {', '.join(REVIEWS)}")
            elif review["verdict"] != "holds" and not review.get("issues"):
                problems.append(f"{review['card']}: a card that does not hold needs its issues")
            elif review["verdict"] == "wrong" and review.get("suggestedVerdict") not in VERDICTS:
                problems.append(f"{review['card']}: a wrong card needs a suggestedVerdict")
            else:
                reviews[review["card"]] = {
                    "verdict": review["verdict"],
                    "issues": [str(issue) for issue in review.get("issues", [])],
                    "suggestedVerdict": review.get("suggestedVerdict"),
                }
        problems += [f"card {card} is not reviewed" for card in sorted(ids - set(reviews))]
        if problems:
            raise ValueError("; ".join(problems[:12]))
        return reviews

    return session.call_checked(role, body, "challenge", check)


# Rendering ------------------------------------------------------------------------------------------------


def render(card: dict[str, Any]) -> str:
    leaders, engineers, plan = card["leaders"], card["engineers"], card["engineers"]["evaluation"]
    licence = card.get("licence")
    review = card.get("review") or {}
    lines = [
        f"# {card['title']}",
        "",
        f"**Verdict: {card['verdict']}.** {card['headline']}",
        "",
        f"Found {card['date']} for the tags {', '.join(card['tags'])} · [{card['url']}]({card['url']})",
    ]
    if card.get("verdictBy") == "sceptic":
        lines += ["", f'The sceptic changed the verdict from "{card["evaluatorVerdict"]}" to "{card["verdict"]}".']
    if licence:
        lines += [
            "",
            f"**Licence:** {licence['spdx'] or 'none found'} ({licence['class']}) - "
            + ("usable." if licence["usable"] else f"**not usable for this profile:** {licence['reason']}."),
        ]
    if "affects" in card:
        lines += [
            "",
            "**May affect:** "
            + (
                "; ".join(f"{entry['profile']} ({entry['component']}): {entry['how']}" for entry in card["affects"])
                or "no profile"
            ),
        ]
    lines += [
        "",
        "## In plain words",
        "",
        f"- **What it is:** {leaders['whatItIs']}",
        f"- **What it could do for us:** {leaders['whatItCouldDo']}",
        f"- **Where it would plug in:** {leaders['wherePlugsIn']}",
        f"- **Why this verdict:** {leaders['why']}",
        "",
        "## For engineers",
        "",
        f"**How it works.** {engineers['howItWorks']}",
        "",
        f"**Component.** {engineers['component']}. Today: {engineers['componentToday']} Replaces: {engineers['replaces']}",
        "",
        f"**Alternatives already in use or available.** {engineers['alternatives']}",
        "",
        f"**Maturity.** {engineers['maturity']}",
        "",
    ]
    for name, title in (("pros", "Pros"), ("cons", "Cons"), ("risks", "Risks")):
        lines += [f"**{title}**", ""] + [f"- {entry}" for entry in engineers[name]] + [""]
    lines += [
        "**How to evaluate it**",
        "",
        f"- Experiment: {plan['experiment']}",
        f"- Metric: {plan['metric']}",
        f"- Pass bar: {plan['passBar']}",
        f"- Effort: {plan['effort']}",
        "",
    ]
    if review:
        lines += (
            ["## Sceptic", "", f"Review: **{review['verdict']}**."]
            + [f"- {issue}" for issue in review.get("issues", [])]
            + [""]
        )
    lines += ["## Evidence", ""] + [f'- {claim["text"]} ("{claim["quote"]}")' for claim in card["claims"]]
    lines += ["", f"Evidence page: {card['evidence']}. Fit rests on: {', '.join(card['profileBasis'])}."]
    return "\n".join(lines) + "\n"


def write_card(root: Path, card: dict[str, Any]) -> None:
    rc.write_json(root / "scout" / "cards" / f"{card['id']}.json", card)
    rc.write_text(root / "scout" / "cards" / f"{card['id']}.md", render(card))


# The run --------------------------------------------------------------------------------------------------


def run(root: Path, config: dict[str, Any], roles: dict[str, str], stamp: str) -> dict[str, Any]:
    """Triage the open candidates, write a card per pick, challenge the cards; returns the run's summary."""
    candidates = open_candidates(root)
    if not candidates:
        return {"triaged": 0, "cards": [], "failures": []}
    with rc.Session(root, "scout", config["calls"]) as session:
        session.say(f"triage: {len(candidates)} open candidates")
        picks = triage(session, root, candidates, config["cardsPerRun"], roles["scoutTriage"])
        picked = {item["key"] for item in picks}
        mark(root, [item["key"] for item in candidates if item["key"] not in picked], "passed", stamp)
        session.say(f"triage: {len(picks)} picked for cards: {', '.join(item['title'] for item in picks) or 'none'}")
        for item in picks:
            item["evidence"] = store_evidence(root, item)

        def job(item: dict[str, Any]):
            def evaluate_one() -> dict[str, Any] | str:
                try:
                    return evaluate(session, root, item, item["evidence"], roles["scoutEvaluator"])
                except (ValueError, rc.RcError, rc.providers.ProviderError) as error:
                    return f"{item['title']}: {error}"

            return evaluate_one

        results = session.parallel([(item["key"], job(item)) for item in picks], workers=3)
        cards, failures = [], []
        for item in picks:
            data = results[item["key"]]
            if isinstance(data, str):
                failures.append(data)
                continue
            cards.append(
                {
                    "id": f"{stamp}-{slug(item['key'])}"[:90],
                    "stamp": stamp,
                    "key": item["key"],
                    "title": item["title"],
                    "url": item["url"],
                    "kind": item["kind"],
                    "date": datetime.date.today().isoformat(),
                    "tags": item["tags"],
                    "triage": item["triage"],
                    "licence": item.get("licence"),
                    "evidence": item["evidence"],
                    "verdict": data["verdict"],
                    "verdictBy": "evaluator",
                    "evaluatorVerdict": data["verdict"],
                    "headline": data["headline"],
                    "leaders": data["leaders"],
                    "engineers": data["engineers"],
                    "claims": data["claims"],
                    "profileBasis": data["profileBasis"],
                    "status": "open",
                    **({"affects": data.get("affects", [])} if is_trends(root) else {}),
                }
            )
        if cards:
            reviews = challenge(session, root, cards, roles["scoutSceptic"])
            for card in cards:
                review = reviews[card["id"]]
                card["review"] = review
                if review["verdict"] == "wrong" and review["suggestedVerdict"] != card["verdict"]:
                    card.update({"verdict": review["suggestedVerdict"], "verdictBy": "sceptic"})
        for card in cards:
            write_card(root, card)
        mark(root, [card["key"] for card in cards], "card", stamp, {card["key"]: card["id"] for card in cards})
        mark(
            root,
            [item["key"] for item in picks if item["key"] not in {card["key"] for card in cards}],
            "candidate",
            stamp,
        )
        session.say(f"scout: {len(cards)} cards, {session.calls} agent calls", "gate")
        return {
            "triaged": len(candidates),
            "cards": [card["id"] for card in cards],
            "failures": failures,
            "calls": session.calls,
        }
