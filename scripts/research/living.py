"""Living topics: a researched topic whose brief has a cadence keeps its searches (watch.json) and is refreshed.

refresh <topic>
  1. search   re-run the saved adapter queries since the last check (no agent)
  2. screen   only records not screened before (screening.json is the seen set; a watched page whose fingerprint
              changed counts as new); retractions are checked first
  3. collect  the researchers read only the new included records; their claims get the next ids, old ids never change
  4. rederive only when new quote-verified evidence entered the ledger: analyze, critique, judge, apply and report
              run again on the whole ledger, the version goes up, and verdicts and rings keep their history
  5. delta    delta/<date>.md: new records, new claims, flipped verdicts, moved rings, and what needs the user's review

A refresh that finds nothing new costs no agent call. An interrupted refresh resumes where it stopped (watch.json
"pending"). An amended brief is not refreshed: ./rc research run redoes it from plan.
See docs/decisions/0009-living-topics.md.
"""

from __future__ import annotations

import datetime
import hashlib
import shutil
from pathlib import Path
from typing import Any

import ingest
import kit
import rc
import research
import sources as registry

WATCH = "watch.json"
# Days between refreshes for "Cadence: derived", from the plan's horizon, clamped to weekly-quarterly.
DERIVED = {"near": 30, "medium": 91, "long": 91}
REDERIVE = ("analyze", "critique", "judge", "apply", "report")


def load_watch(directory: Path) -> dict[str, Any] | None:
    path = directory / WATCH
    return rc.load_json(path) if path.is_file() else None


def save_watch(directory: Path, watch: dict[str, Any]) -> None:
    rc.write_json(directory / WATCH, watch)


def cadence_days(cadence: str, horizon: str | None) -> int:
    days = research.CADENCES.get(cadence, 0)
    return min(max(DERIVED.get(horizon or "", 30), 7), 91) if days < 0 else days


def watch_queries(root: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The plan's adapter avenues whose adapter can be watched; the web avenues are the researchers' and are not saved."""
    adapters = registry.descriptors(root)
    return [{"avenue": number, "adapter": avenue["adapter"], "query": avenue["query"], "filters": avenue.get("filters") or {},
             "questions": avenue["questions"]}
            for number, avenue in enumerate(plan["avenues"], 1)
            if avenue["adapter"] in adapters and adapters[avenue["adapter"]].get("watchable")]


def begin_run(root: Path, topic: str) -> None:
    """A full run of a living topic produces the next version; a resumed run keeps the version it started."""
    directory = research.topic_dir(root, topic)
    watch = load_watch(directory)
    if watch and not watch.get("running"):
        save_watch(directory, {**watch, "version": watch["version"] + 1, "running": True, "pending": None})


def after_run(root: Path, topic: str) -> dict[str, Any] | None:
    """After a complete run: save the searches to watch and mark the topic living, unless its cadence is none."""
    directory = research.topic_dir(root, topic)
    text = (directory / "brief.md").read_text(encoding="utf-8")
    living = research.brief_living(text)
    plan = rc.load_json(directory / "source-plan.json")
    days = cadence_days(living["cadence"], plan.get("horizon"))
    previous = load_watch(directory)
    if not days:
        (directory / WATCH).unlink(missing_ok=True)
        return None
    today = rc.today()
    watch = {
        "cadence": living["cadence"], "cadenceDays": days, "retireWhen": living["retireWhen"], "briefHash": research.brief_hash(text),
        "version": previous["version"] if previous else 1, "running": False, "pending": None,
        "lastChecked": today, "lastChanged": today, "queries": watch_queries(root, plan),
        "log": [*(previous or {}).get("log", []), {"date": today, "version": previous["version"] if previous else 1, "kind": "run"}],
    }
    save_watch(directory, watch)
    if research.brief_status(text) in ("accepted", "living"):
        research.set_status(root, topic, "living")
    stamp_report(directory, watch)
    return watch


def stamp_report(directory: Path, watch: dict[str, Any]) -> None:
    """Put the version and the check dates on the report's header line."""
    report = directory / "report.md"
    if not report.is_file():
        return
    lines = report.read_text(encoding="utf-8").split("\n")
    for index, line in enumerate(lines):
        if line.startswith("Topic: "):
            base = line.split(" · Version ", 1)[0]
            lines[index] = f"{base} · Version {watch['version']} · Checked {watch['lastChecked']} · Changed {watch['lastChanged']}"
            break
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def is_due(watch: dict[str, Any], today: datetime.date) -> bool:
    return datetime.date.fromisoformat(watch["lastChecked"]) + datetime.timedelta(days=watch["cadenceDays"]) <= today


def due(root: Path) -> list[str]:
    """Living topics whose cadence has elapsed since their last check."""
    today = datetime.date.fromisoformat(rc.today())
    topics = []
    for path in sorted((root / "research").glob(f"*/{WATCH}")):
        status = research.brief_status((path.parent / "brief.md").read_text(encoding="utf-8"))
        if status == "living" and is_due(rc.load_json(path), today):
            topics.append(path.parent.name)
    return topics


# Refresh ----------------------------------------------------------------------------------------------------


def snapshot(directory: Path) -> dict[str, Any]:
    """The conclusions before a refresh, for the delta."""
    def read(name: str, field: str) -> list[dict[str, Any]]:
        return rc.load_json(directory / name).get(field, []) if (directory / name).is_file() else []
    judgement = rc.load_json(directory / "judgement.json") if (directory / "judgement.json").is_file() else {}
    return {"claims": {item["claim"]: item["verdict"] for item in judgement.get("claims", [])},
            "ideas": {item["idea"]: item["verdict"] for item in judgement.get("ideas", [])},
            "contested": [item["claim"] for item in judgement.get("contested", [])],
            "rings": {fit["idea"]: fit["ring"] for fit in read("fit.json", "fits")},
            "names": {idea["id"]: idea["name"] for idea in read("ideas.json", "ideas")}}


def search_new(session: rc.Session, root: Path, topic: str, watch: dict[str, Any], log: Path) -> tuple[list[dict[str, Any]], int]:
    """Run the saved queries since the last check; return the records not screened before, numbered on, and the
    number of results."""
    directory = research.topic_dir(root, topic)
    limit = rc.settings(root)["research"].get("resultsPerQuery", 20)
    found = []
    for query in watch["queries"]:
        try:
            records = registry.search(root, query["adapter"], query["query"], query["filters"], watch["lastChecked"], limit, log)
        except kit.AdapterError as error:
            session.say(f"refresh search {query['avenue']} ({query['adapter']}): failed, {error}", "warn")
            continue
        found += [{**item, "questions": query["questions"]} for item in records]
    rows = rc.load_json(directory / "screening.json")["records"]
    seen = {row["key"]: row for row in rows}
    fresh = []
    for item in registry.merge(found):
        before = seen.get(item["key"])
        fingerprint = item["extra"].get("sha256")
        if before and not (fingerprint and before.get("fingerprint") and fingerprint != before["fingerprint"]):
            continue
        fresh.append({**item, "changed": bool(before), "hop": 0, "via": [],
                      "questions": sorted({q for other in found if other["key"] == item["key"] for q in other["questions"]})})
    start = max((int(row["id"][1:]) for row in rows), default=0) + 1
    for offset, item in enumerate(fresh):
        item["id"] = f"R{start + offset}"
    return fresh, len(found)


def recheck(session: rc.Session, root: Path, topic: str) -> list[str]:
    """Fetch again every stored page whose evidence type's half-life has passed since it was last checked. A claim
    whose quote the page no longer holds, or whose page is gone, is marked drifted. Scholarly records (stored as
    abstracts) are not re-fetched: retractions cover what changes there. Returns the drifted claim ids."""
    directory = research.topic_dir(root, topic)
    led = research.ledger(root, topic)
    types = research.evidence_types(root)
    families = {identifier: spec["family"] for identifier, spec in registry.descriptors(root).items()}
    screened = {row["id"]: row for row in rc.load_json(directory / "screening.json")["records"]} if (directory / "screening.json").is_file() else {}
    today = datetime.date.fromisoformat(rc.today())
    drifted = []
    for source in led["sources"]:
        checked = source.get("checkedAt")
        half_life = types.get(source.get("evidenceType", "unknown"), types["unknown"])["halfLifeDays"]
        if not source.get("stored") or not checked or datetime.date.fromisoformat(checked) + datetime.timedelta(days=half_life) > today:
            continue
        row = screened.get(source.get("record"), {})
        if any(families.get(adapter) in ("scholarly", "books") for adapter in row.get("foundBy", [])):
            source["checkedAt"] = rc.today()
            continue
        try:
            _, text, extractor, data = ingest.url_document(source["url"])
        except Exception as error:  # noqa: BLE001 - any failure to fetch means the page is no longer what was checked
            text, reason = None, f"the page could not be fetched again ({str(error)[:120]})"
        for claim in led["claims"]:
            if claim["source"] != source["id"] or not claim["quoteVerified"]:
                continue
            if text is None or not research.quote_found(claim["quote"], text):
                claim.update({"quoteVerified": False, "drifted": {"at": rc.today(), "reason": reason if text is None else
                              "the page no longer contains the quote"}})
                drifted.append(claim["id"])
        if text is not None:
            # Keep the page as it reads now: that is what the claims were checked against today.
            source_id, name = source["stored"].split("/")[1], source["stored"].split("/text/", 1)[1]
            descriptor = rc.load_json(ingest.source_path(root, source_id))
            entries = {name: {"origin": source["url"], "sha256": hashlib.sha256(data).hexdigest(), "extractor": extractor}}
            research.store_appending(root, descriptor, entries, {name: text}, [], append=True)
        source["checkedAt"] = rc.today()
    if drifted:
        session.say(f"refresh: {len(drifted)} claims drifted: {', '.join(drifted)}", "warn")
    rc.write_json(directory / "claims.json", led)
    rc.write_text(directory / "claims.md", research.render_ledger(led))
    return drifted


def screen_new(session: rc.Session, root: Path, topic: str, fresh: list[dict[str, Any]], stamp: str, log: Path) -> list[dict[str, Any]]:
    """Screen the new records like the first run did, store the included ones, and append them to screening.json."""
    directory = research.topic_dir(root, topic)
    plan = rc.load_json(directory / "source-plan.json")
    check = research.mark_retractions(session, root, fresh, log)
    decisions = research.screen_hop(session, root, topic, fresh, "r", plan)
    included = [item for item in fresh if decisions[item["id"]]["decision"] == "include"]
    if included:
        research.store_included(root, topic, included, append=True)
    screening = rc.load_json(directory / "screening.json")
    stored = {item["id"]: item.get("stored") for item in included}
    rows = [{"id": item["id"], "key": item["key"], "title": item["title"], "url": item["url"], "doi": item["doi"],
             "foundBy": item["foundBy"], "hop": 0, "via": [], "evidenceType": item["evidenceType"],
             "fingerprint": item["extra"].get("sha256"), "addedAt": stamp, "changed": item["changed"],
             **decisions[item["id"]], "stored": stored.get(item["id"])} for item in fresh]
    screening["records"] += rows
    screening["retractionCheck"] = [*screening.get("retractionCheck", []), f"refresh {stamp}: {check}"]
    rc.write_json(directory / "screening.json", screening)
    rc.write_text(directory / "screening.md", research.render_screening(topic, screening["flow"], screening["criteria"],
                                                                        screening["records"], screening["retractionCheck"]))
    return rows


def refresh(root: Path, topic: str, budget: int | None = None) -> dict[str, Any]:
    """Refresh one living topic; returns the delta it wrote."""
    research.require_scope(root)
    directory = research.topic_dir(root, topic)
    text = (directory / "brief.md").read_text(encoding="utf-8")
    status = research.brief_status(text)
    if status in ("paused", "retired"):
        raise rc.RcError(f"research/{topic} is {status}; " + ("./rc research resume it first" if status == "paused" else "it is not refreshed any more"))
    watch = load_watch(directory)
    if watch is None or not (directory / "report.md").is_file():
        raise rc.RcError(f"research/{topic} is not living: give its brief a Living cadence and finish ./rc research run {topic}")
    if watch.get("running"):
        raise rc.RcError(f"research/{topic} has an unfinished run; finish it with ./rc research run {topic}")
    if research.brief_hash(text) != watch["briefHash"]:
        raise rc.RcError(f"research/{topic}/brief.md was amended after version {watch['version']}; ./rc research run {topic} "
                         "redoes the research from plan, since the amendment changes what is searched")
    ingest.guard(root)
    config = rc.settings(root)
    pending = watch.get("pending") or {}
    stamp = pending.get("stamp") or delta_stamp(directory)
    before_path = root / ".rc-local" / "research" / topic / f"refresh-{stamp}-before.json"
    log = directory / "delta" / f"{stamp}-searches.json"
    with rc.Session(root, f"refresh-{topic}", budget or config["budget"].get("refreshCalls", 16)) as session:
        session.replies = research.replies_dir(root, topic, f"refresh-{stamp}")
        if not pending:
            rc.write_json(before_path, snapshot(directory))
            log.unlink(missing_ok=True)
            drifted = recheck(session, root, topic)
            fresh, identified = search_new(session, root, topic, watch, log)
            session.say(f"refresh: {identified} results, {len(fresh)} not screened before")
            rows = screen_new(session, root, topic, fresh, stamp, log) if fresh else []
            pending = {"stamp": stamp, "step": "screened", "identified": identified, "records": [row["id"] for row in rows], "added": [],
                       "drifted": drifted}
            save_watch(directory, {**watch, "pending": pending})
        rows = [row for row in rc.load_json(directory / "screening.json")["records"] if row["id"] in pending["records"]]
        included = [row for row in rows if row["decision"] == "include"]
        if pending["step"] == "screened":
            added = research.stage_collect(session, root, topic, only=included) if included else []
            pending = {**pending, "step": "collected", "added": [claim["id"] for claim in added]}
            save_watch(directory, {**watch, "pending": pending})
        claims = {claim["id"]: claim for claim in research.ledger(root, topic)["claims"]}
        verified = [identifier for identifier in pending["added"] if claims[identifier]["quoteVerified"]]
        # Drifted evidence the conclusions rest on is as material as new evidence: both are re-critiqued.
        relied_on = set(research.cited_claims(root, topic)) & set(pending.get("drifted", []))
        material = bool(verified or relied_on)
        if material and pending["step"] == "collected":
            watch = {**watch, "version": watch["version"] + 1, "pending": {**pending, "step": "rederiving"}}
            # The new claims are what makes the next version; collect ran before it was known there would be one.
            led = research.ledger(root, topic)
            for claim in led["claims"]:
                if claim["id"] in pending["added"]:
                    claim["addedIn"] = watch["version"]
            rc.write_json(directory / "claims.json", led)
            save_watch(directory, watch)
            pending = watch["pending"]
        if pending["step"] == "rederiving":
            for stage in REDERIVE:
                session.say(f"refresh: re-deriving {stage} with the new evidence")
                research.RUNNERS[stage](session, root, topic)
        before = rc.load_json(before_path)
        delta = build_delta(directory, topic, stamp, watch, pending, rows, claims, before, material)
        today = rc.today()
        watch = {**watch, "pending": None, "lastChecked": today, "lastChanged": today if material else watch["lastChanged"],
                 "log": [*watch.get("log", []), {"date": today, "version": watch["version"], "kind": "refresh", "material": material}]}
        save_watch(directory, watch)
        write_delta(directory, stamp, delta, watch)
        stamp_report(directory, watch)
        if status == "accepted":
            research.set_status(root, topic, "living")
        shutil.rmtree(session.replies, ignore_errors=True)
        before_path.unlink(missing_ok=True)
        session.say(f"refresh of {topic}: {delta['summary']} (research/{topic}/delta/{stamp}.md, {session.calls} agent calls)", "gate")
    return delta


def delta_stamp(directory: Path) -> str:
    stamp, number = rc.today(), 1
    while (directory / "delta" / f"{stamp}.md").exists():
        number += 1
        stamp = f"{rc.today()}-{number}"
    return stamp


def build_delta(directory: Path, topic: str, stamp: str, watch: dict[str, Any], pending: dict[str, Any], rows: list[dict[str, Any]],
                claims: dict[str, dict[str, Any]], before: dict[str, Any], material: bool) -> dict[str, Any]:
    after = snapshot(directory)
    added = [claims[identifier] for identifier in pending["added"]]
    flips = [{"claim": key, "from": value, "to": after["claims"][key]} for key, value in before["claims"].items()
             if key in after["claims"] and after["claims"][key] != value]
    idea_flips = [{"idea": key, "from": value, "to": after["ideas"][key]} for key, value in before["ideas"].items()
                  if key in after["ideas"] and after["ideas"][key] != value]
    moves = [{"idea": key, "from": before["rings"].get(key, "new"), "to": ring} for key, ring in after["rings"].items()
             if before["rings"].get(key) != ring]
    contested = [claim for claim in after["contested"] if claim not in before["contested"]]
    drifted = [claims[identifier] for identifier in pending.get("drifted", [])]
    review = bool(flips or idea_flips or moves or contested or drifted)
    if material:
        summary = "material change: " + ("verdicts or rings moved, see Needs your review" if flips or idea_flips or moves or contested
                                         else "new or drifted evidence, conclusions unchanged")
    elif drifted:
        summary = "no material change: some evidence drifted, none the conclusions rest on"
    elif not rows:
        summary = "no material change: nothing new was found"
    else:
        summary = "no material change: new records, but no new verified evidence"
    return {"topic": topic, "stamp": stamp, "version": watch["version"], "since": watch["lastChecked"], "material": material,
            "summary": summary, "identified": pending.get("identified", 0), "records": rows, "added": added, "flips": flips,
            "ideaFlips": idea_flips, "moves": moves, "contested": contested, "drifted": drifted, "names": after["names"] or before["names"]}


def write_delta(directory: Path, stamp: str, delta: dict[str, Any], watch: dict[str, Any]) -> None:
    rc.write_json(directory / "delta" / f"{stamp}.json", delta)
    cell, names = research.cell, delta["names"]
    lines = [f"# Delta: {delta['topic']}, {stamp}\n", f"Version {delta['version']} · searched since {delta['since']} · "
             f"{delta['identified']} results, {len(delta['records'])} not screened before\n", f"**{delta['summary'][0].upper()}{delta['summary'][1:]}.**"]
    review = [f"- {item['claim']}: {item['from']} → {item['to']}" for item in delta["flips"]]
    review += [f"- Idea {item['idea']} ({names.get(item['idea'], '')}): {item['from']} → {item['to']}" for item in delta["ideaFlips"]]
    review += [f"- Idea {item['idea']} ({names.get(item['idea'], '')}) moved {item['from']} → {item['to']}" for item in delta["moves"]]
    review += [f"- {claim}: newly contested (a reviewer refuted it, the judge kept it)" for claim in delta["contested"]]
    review += [f"- {claim['id']}: drifted, {claim['drifted']['reason']}" for claim in delta.get("drifted", [])]
    if review:
        lines += ["", "## Needs your review", "", "These changed since the previous version. Check them before relying on the report.", "", *review]
    if delta["records"]:
        lines += ["", "## New records", "", "| Record | Title | Decision | Reason |", "| --- | --- | --- | --- |"]
        lines += [f"| {row['id']} | [{cell(row['title'])}]({row['url']}){' (changed page)' if row.get('changed') else ''} | "
                  f"{row['decision']}{' ' + row['criterion'] if row.get('criterion') else ''} | {cell(row['reason'])} |" for row in delta["records"]]
    if delta["added"]:
        lines += ["", "## New claims", "", "| Claim | Text | Quote verified |", "| --- | --- | --- |"]
        lines += [f"| {claim['id']} | {cell(claim['text'])} | {'yes' if claim['quoteVerified'] else 'no'} |" for claim in delta["added"]]
    lines += ["", f"Retire when: {watch['retireWhen'].rstrip('.')}. If that has happened, `./rc research retire {delta['topic']}`.",
              f"Next refresh due {(datetime.date.fromisoformat(watch['lastChecked']) + datetime.timedelta(days=watch['cadenceDays'])).isoformat()}."]
    rc.write_text(directory / "delta" / f"{stamp}.md", "\n".join(lines))


def refresh_due(root: Path, budget: int | None = None) -> int:
    """Refresh every due topic; one topic's failure is reported and the others still run."""
    topics, failed = due(root), []
    if not topics:
        print("no living topic is due")
    for topic in topics:
        try:
            refresh(root, topic, budget)
        except (rc.RcError, rc.providers.ProviderError, OSError, ValueError, KeyError) as error:
            print(f"error: refresh of {topic} failed: {error}")
            failed.append(topic)
    return 1 if failed else 0
