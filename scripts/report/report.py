#!/usr/bin/env python3
"""./rc report [<topic>]: research as self-contained HTML pages for people without the repository. With a topic, its
page; without, a dashboard of the use case's topics (index.html) with every topic's page beside it.

The page is computed from the topic's committed outputs, never written by an agent, so it costs no budget and the
same outputs always give the same bytes. The first screen is for decisions: the bottom line, the ideas by ring with
the judge's verdict, and each question's certainty. Below it is the evidence: the screening funnel, claim verdicts
and source reliability, the hypothesis matrices, assumptions, the full report with every [C#] linked to its claim,
the claims and sources, and a living topic's history. A stage that has not run is shown as missing, never guessed.

Pages go to <data root>/.rc-local/reports/ through rc.write_text, so secrets are redacted like every runner write.
Markdown is rendered with raw HTML off and every other value is escaped: text from the web stays text.
See docs/decisions/0014-report-pages.md.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "research"), str(HERE.parent / "runner"), str(HERE.parent / "ingest"), str(HERE.parent / "sources")]
from markdown_it import MarkdownIt  # noqa: E402

import rc  # noqa: E402
import research  # noqa: E402

RING_ORDER = {ring: index for index, ring in enumerate(research.RINGS)}
VERDICT_ORDER = {verdict: index for index, verdict in enumerate(research.IDEA_VERDICTS)}
RATING_NAMES = {"C": "consistent", "I": "inconsistent", "N": "neutral"}
MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable("table")
REF_GROUP = re.compile(r"\[(C\d+(?:\s*[,;]\s*C\d+)*)\]")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def safe_url(url: Any) -> str | None:
    return url if isinstance(url, str) and re.match(r"https?://", url, re.IGNORECASE) else None


def link(url: Any, text: Any) -> str:
    target = safe_url(url)
    return f'<a href="{esc(target)}" rel="noopener noreferrer">{esc(text)}</a>' if target else esc(text)


def load(directory: Path, name: str) -> Any:
    path = directory / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def read(directory: Path, name: str) -> str | None:
    path = directory / name
    return path.read_text(encoding="utf-8") if path.is_file() else None


class Topic:
    """A topic's outputs, loaded once; every field may be missing when its stage has not run."""

    def __init__(self, root: Path, topic: str) -> None:
        self.root, self.id = root, topic
        self.dir = research.topic_dir(root, topic)
        if not (self.dir / "brief.md").is_file():
            raise rc.RcError(f"no topic {topic}: research/{topic}/brief.md is missing")
        self.brief = read(self.dir, "brief.md") or ""
        self.plan = load(self.dir, "source-plan.json") or {}
        self.screening = load(self.dir, "screening.json")
        self.ledger = load(self.dir, "claims.json")
        self.ideas = load(self.dir, "ideas.json")
        self.judgement = load(self.dir, "judgement.json")
        self.fit = load(self.dir, "fit.json")
        self.watch = load(self.dir, "watch.json")
        self.report = read(self.dir, "report.md")
        self.usecase = load(root, "usecase.json")
        self.claims = {claim["id"]: claim for claim in (self.ledger or {}).get("claims", [])}
        self.sources = {source["id"]: source for source in (self.ledger or {}).get("sources", [])}
        self.verdicts = {item["claim"]: item for item in (self.judgement or {}).get("claims", [])}
        self.questions = dict(research.QUESTION.findall(research.sections(self.brief).get("Questions", "")))

    @property
    def title(self) -> str:
        match = re.search(r"^# (.+)$", self.brief, re.MULTILINE)
        return match.group(1).strip() if match else self.id

    @property
    def status(self) -> str:
        return research.brief_status(self.brief)

    def report_parts(self) -> tuple[str, dict[str, str]]:
        """The report's metadata line and its sections by heading."""
        if not self.report:
            return "", {}
        head, *_ = self.report.split("\n## ", 1)
        meta = next((line for line in head.splitlines()[1:] if line.strip()), "")
        parts = re.split(r"^## (.+)$", self.report, flags=re.MULTILINE)
        return meta.strip(), {heading.strip(): body.strip() for heading, body in zip(parts[1::2], parts[2::2])}


# Pieces ---------------------------------------------------------------------------------------------------


def claim_title(topic: Topic, claim_id: str) -> str:
    claim = topic.claims.get(claim_id)
    if not claim:
        return "not in the ledger"
    verdict = topic.verdicts.get(claim_id, {}).get("verdict", "not judged")
    return f"{claim['text']} ({verdict})"


def linked_refs(topic: Topic, rendered: str) -> str:
    """[C1, C2] in rendered HTML becomes links to the claims appendix, each with the claim as its tooltip."""
    def one(claim_id: str) -> str:
        verdict = topic.verdicts.get(claim_id, {}).get("verdict", "")
        return (f'<a class="cref cv-{esc(verdict.lower() or "none")}" href="#{esc(claim_id)}" '
                f'title="{esc(claim_title(topic, claim_id))}">{esc(claim_id)}</a>')

    def group(match: re.Match[str]) -> str:
        return "[" + ", ".join(one(claim_id) for claim_id in re.split(r"\s*[,;]\s*", match.group(1))) + "]"
    return REF_GROUP.sub(group, rendered)


def markdown(topic: Topic, text: str) -> str:
    return linked_refs(topic, MARKDOWN.render(text))


def refs(topic: Topic, ids: list[str]) -> str:
    return linked_refs(topic, esc("[" + ", ".join(ids) + "]")) if ids else ""


def badge(kind: str, value: Any) -> str:
    text = str(value)
    return f'<span class="badge {kind}-{esc(text.lower().replace(" ", "-"))}">{esc(text)}</span>'


def missing(stage: str) -> str:
    return f'<p class="missing">Not produced yet: the {esc(stage)} stage has not run for this topic.</p>'


def bars(rows: list[tuple[str, int, str]], total: int | None = None) -> str:
    """Horizontal bars: (label, count, css class); widths relative to the largest count or the total."""
    top = total or max((count for _, count, _ in rows), default=0) or 1
    items = "".join(f'<div class="bar-row"><span class="bar-label">{label}</span>'
                    f'<span class="bar-track"><span class="bar {css}" style="width:{max(count / top * 100, 0.5 if count else 0):.1f}%"></span></span>'
                    f'<span class="bar-count">{count}</span></div>' for label, count, css in rows)
    return f'<div class="bars">{items}</div>'


def stacked(parts: list[tuple[str, int, str]]) -> str:
    total = sum(count for _, count, _ in parts) or 1
    segments = "".join(f'<span class="seg {css}" style="width:{count / total * 100:.2f}%" title="{esc(label)}: {count}"></span>'
                       for label, count, css in parts if count)
    legend = "".join(f'<span class="key"><span class="dot {css}"></span>{esc(label)} {count}</span>' for label, count, css in parts if count)
    return f'<div class="stack">{segments}</div><div class="legend">{legend}</div>'


# Sections -------------------------------------------------------------------------------------------------


def section_header(topic: Topic) -> str:
    meta, _ = topic.report_parts()
    usecase = topic.usecase or {}
    crumbs = esc(usecase.get("title") or usecase.get("id") or "")
    counts = []
    if topic.ledger:
        counts.append(f"{len(topic.claims)} claims from {len(topic.sources)} sources")
    if topic.screening:
        flow = topic.screening.get("flow", {})
        counts.append(f"{flow.get('included', 0)} of {flow.get('screened', 0)} screened records included")
    line = esc(meta) if meta else f"Topic: {esc(topic.id)}"
    return (f'<header class="top"><p class="crumbs">{crumbs}</p><h1>{esc(topic.title)}</h1>'
            f'<p class="meta">{line} {badge("status", topic.status)}</p>'
            + (f'<p class="meta">{esc(" · ".join(counts))}</p>' if counts else "") + "</header>")


def section_bottom_line(topic: Topic) -> str:
    _, parts = topic.report_parts()
    body = parts.get("TL;DR")
    content = markdown(topic, body) if body else missing("report")
    return f'<section id="bottom-line" class="lead"><h2>Bottom line</h2>{content}</section>'


def idea_rows(topic: Topic) -> list[dict[str, Any]]:
    judged = {item["idea"]: item for item in (topic.judgement or {}).get("ideas", [])}
    fits = {item["idea"]: item for item in (topic.fit or {}).get("fits", [])}
    rows = [{**idea, "judged": judged.get(idea["id"], {}), "fit": fits.get(idea["id"], {})} for idea in (topic.ideas or {}).get("ideas", [])]
    return sorted(rows, key=lambda row: (RING_ORDER.get(row["fit"].get("ring"), len(RING_ORDER)),
                                         VERDICT_ORDER.get(row["judged"].get("verdict"), len(VERDICT_ORDER)), int(row["id"][1:])))


def trail(history: list[dict[str, Any]], field: str) -> str:
    if len(history) < 2:
        return ""
    return '<p class="trail">History: ' + " → ".join(f"{esc(item[field])} ({esc(item['date'])})" for item in history) + "</p>"


def section_ideas(topic: Topic) -> str:
    if not topic.ideas:
        return f'<section id="ideas"><h2>Ideas</h2>{missing("analyze")}</section>'
    cards = []
    for row in idea_rows(topic):
        fit, judged = row["fit"], row["judged"]
        head = (f'<div class="card-head"><span class="idea-id">{esc(row["id"])}</span><h3>{esc(row["name"])}</h3>'
                + (badge("ring", fit["ring"]) if fit.get("ring") else badge("ring", "not applied"))
                + (badge("verdict", judged["verdict"]) if judged.get("verdict") else "")
                + (badge("effort", f"effort {fit['effort']}") if fit.get("effort") else "") + "</div>")
        facts = [("What it is", esc(row.get("summary", "")) + " " + refs(topic, row.get("claims", [])))]
        if fit.get("replaces"):
            facts.append(("Replaces", esc(fit["replaces"])))
        if fit.get("nextStep"):
            facts.append(("Next step", esc(fit["nextStep"])))
        if fit.get("risks"):
            facts.append(("Risks", esc(fit["risks"])))
        if judged.get("reason"):
            facts.append(("Judge", linked_refs(topic, esc(judged["reason"]))))
        detail = "".join(f"<dt>{name}</dt><dd>{value}</dd>" for name, value in facts)
        why = (f'<details><summary>Why this ring</summary><div class="md">{markdown(topic, fit["rationale"])}</div></details>'
               if fit.get("rationale") else "")
        history = trail(fit.get("history", []), "ring") + trail(judged.get("history", []), "verdict")
        cards.append(f'<article class="card ring-{esc((fit.get("ring") or "none").lower())}">{head}<dl>{detail}</dl>{why}{history}</article>')
    note = "" if topic.fit else '<p class="missing">Rings come from the apply stage, which has not run yet.</p>'
    return f'<section id="ideas"><h2>Ideas</h2>{note}<div class="cards">{"".join(cards)}</div></section>'


def section_answers(topic: Topic) -> str:
    answers = {item["question"]: item for item in (topic.judgement or {}).get("answers", [])}
    if not topic.questions:
        return ""
    rows = []
    for question, text in topic.questions.items():
        answer = answers.get(question)
        if not answer:
            rows.append(f'<div class="answer"><p class="q"><b>{esc(question)}</b> {esc(text)}</p><p class="missing">Not judged yet.</p></div>')
            continue
        reasons = "".join(f'<li><span class="down">−{esc(item["levels"])} {esc(item["domain"])}</span> {linked_refs(topic, esc(item["reason"]))} {refs(topic, item.get("claims", []))}</li>'
                          for item in answer.get("downgrades", []))
        reasons += "".join(f'<li><span class="up">+{esc(item["levels"])} {esc(item["domain"])}</span> {linked_refs(topic, esc(item["reason"]))} {refs(topic, item.get("claims", []))}</li>'
                           for item in answer.get("upgrades", []))
        rows.append(f'<div class="answer"><p class="q"><b>{esc(question)}</b> {esc(text)}</p>'
                    f'<p>Certainty {badge("certainty", answer["certainty"])}</p>' + (f"<ul>{reasons}</ul>" if reasons else "") + "</div>")
    notes = (topic.judgement or {}).get("notes")
    notes_html = f'<p class="note"><b>Judge\'s note:</b> {linked_refs(topic, esc(notes))}</p>' if notes else ""
    return f'<section id="answers"><h2>How sure we are</h2>{"".join(rows)}{notes_html}</section>'


def section_evidence(topic: Topic) -> str:
    blocks = []
    if topic.screening:
        flow = topic.screening.get("flow", {})
        criteria = {item["id"]: item for item in topic.screening.get("criteria", [])}
        funnel = [("Found by searches", flow.get("identified", 0), "b-found"),
                  ("Found by following citations", flow.get("citationIdentified", 0), "b-found"),
                  ("Duplicates removed", flow.get("duplicates", 0) + flow.get("citationDuplicates", 0), "b-muted"),
                  ("Screened", flow.get("screened", 0), "b-screen"),
                  ("Excluded", flow.get("excluded", 0), "b-out"),
                  ("Included", flow.get("included", 0), "b-in")]
        reasons = sorted(flow.get("excludedBy", {}).items(), key=lambda item: -item[1])
        reason_rows = [(f"{esc(key)} {esc(criteria.get(key, {}).get('text', key))}", count, "b-out") for key, count in reasons]
        blocks.append('<div class="panel"><h3>Screening</h3>' + bars(funnel)
                      + ('<h4>Why records were excluded</h4>' + bars(reason_rows) if reason_rows else "") + "</div>")
    else:
        blocks.append(f'<div class="panel"><h3>Screening</h3>{missing("screen")}</div>')
    if topic.ledger:
        counts = {verdict: 0 for verdict in (*research.CLAIM_VERDICTS, "not judged")}
        for claim_id in topic.claims:
            counts[topic.verdicts.get(claim_id, {}).get("verdict", "not judged")] += 1
        verdicts = stacked([(verdict, count, f"v-{verdict.lower().replace(' ', '-')}") for verdict, count in counts.items()])
        grades = [(grade, sum(source.get("reliability") == grade for source in topic.sources.values()), f"g-{grade.lower()}") for grade in research.GRADES]
        types: dict[str, int] = {}
        for source in topic.sources.values():
            types[source.get("evidenceType", "unknown")] = types.get(source.get("evidenceType", "unknown"), 0) + 1
        type_rows = [(esc(name), count, "b-found") for name, count in sorted(types.items(), key=lambda item: (-item[1], item[0]))]
        blocks.append('<div class="panel"><h3>Claims</h3><p class="hint">Verdicts after the sceptics and the judge. Claims the answer '
                      'does not rely on are not judged.</p>' + verdicts
                      + '<h3>Sources</h3><p class="hint">Reliability A (best) to F, capped by evidence type.</p>' + bars(grades)
                      + "<h4>Evidence types</h4>" + bars(type_rows) + "</div>")
    else:
        blocks.append(f'<div class="panel"><h3>Claims</h3>{missing("collect")}</div>')
    return f'<section id="evidence"><h2>Evidence at a glance</h2><div class="panels">{"".join(blocks)}</div></section>'


def section_hypotheses(topic: Topic) -> str:
    statements = {item["id"]: item["statement"] for item in topic.plan.get("hypotheses", [])}
    assumption_verdicts = {item["assumption"]: item for item in (topic.judgement or {}).get("assumptions", [])}
    verdicts = {claim_id: item.get("verdict") for claim_id, item in topic.verdicts.items()}
    if not topic.ideas:
        return f'<section id="hypotheses"><h2>Competing hypotheses</h2>{missing("analyze")}</section>'
    entries = {entry["question"]: entry for entry in topic.ideas.get("questions", [])}
    parts = []
    for question in topic.questions or entries:
        entry = entries.get(question, {})
        body = [f'<h3>{esc(question)} {esc(topic.questions.get(question, ""))}</h3>']
        ach = entry.get("ach")
        if ach:
            ranking, diagnostic = research.ach_ranking(ach, verdicts)
            body.append("<ol class=\"ranking\">" + "".join(
                f'<li><b>{esc(hypothesis)}</b> {esc(statements.get(hypothesis, ""))} '
                f'<span class="hint">{score} inconsistent claim{"s" if score != 1 else ""}</span></li>' for hypothesis, score in ranking) + "</ol>")
            body.append('<p class="hint">Ranked by how much surviving evidence is inconsistent with each hypothesis (fewest first). '
                        'Struck-out claims were refuted or unsupported and do not count.</p>')
            header = "".join(f'<th title="{esc(statements.get(hypothesis, ""))}">{esc(hypothesis)}</th>' for hypothesis in ach["hypotheses"])
            rows = []
            for row in ach["matrix"]:
                out = verdicts.get(row["claim"]) in ("REFUTED", "UNSUPPORTED")
                cells = "".join(f'<td class="r-{esc(row["ratings"].get(hypothesis, "").lower())}" title="{esc(RATING_NAMES.get(row["ratings"].get(hypothesis), ""))}">'
                                f'{esc(row["ratings"].get(hypothesis, ""))}</td>' for hypothesis in ach["hypotheses"])
                mark = ' <span class="hint">diagnostic</span>' if row["claim"] in diagnostic else ""
                rows.append(f'<tr class="{"out" if out else ""}"><th scope="row">{refs(topic, [row["claim"]])}{mark}'
                            f'<span class="claim-text">{esc(topic.claims.get(row["claim"], {}).get("text", ""))}</span></th>{cells}</tr>')
            body.append(f'<div class="scroll"><table class="ach"><thead><tr><th>Claim</th>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
            body.append('<p class="legend"><span class="key"><span class="dot r-c"></span>C consistent</span>'
                        '<span class="key"><span class="dot r-i"></span>I inconsistent</span><span class="key"><span class="dot r-n"></span>N neutral</span></p>')
            body += [f'<p class="note">Untested alternative (no search looked for evidence against it): {esc(item)}</p>' for item in ach.get("untested", [])]
        else:
            no_alternative = next((item for item in topic.plan.get("noAlternatives", []) if item.get("question") == question), None)
            body.append(f'<p class="hint">No competing hypotheses: {esc(no_alternative["why"])}</p>' if no_alternative
                        else '<p class="hint">This question has no hypothesis matrix (the topic ran before matrices were required).</p>')
        assumptions = entry.get("assumptions", [])
        if assumptions:
            items = "".join(f'<li>{badge("verdict", assumption_verdicts[item["id"]]["verdict"]) if item["id"] in assumption_verdicts else ""} '
                            f'<b>{esc(item["id"])}</b> {esc(item["text"])} {refs(topic, item.get("claims", []))}'
                            + (f'<br><span class="hint">{linked_refs(topic, esc(assumption_verdicts[item["id"]]["reason"]))}</span>' if item["id"] in assumption_verdicts else "")
                            + "</li>" for item in assumptions)
            body.append(f'<h4>Key assumptions</h4><ul class="assumptions">{items}</ul>')
        parts.append(f'<div class="question">{"".join(body)}</div>')
    return f'<section id="hypotheses"><h2>Competing hypotheses and assumptions</h2>{"".join(parts)}</section>'


def section_report(topic: Topic) -> str:
    _, parts = topic.report_parts()
    rest = {heading: body for heading, body in parts.items() if heading != "TL;DR"}
    if not rest:
        return ""
    text = "\n\n".join(f"## {heading}\n\n{body}" for heading, body in rest.items())
    return f'<section id="report"><details><summary><h2>Full report</h2></summary><div class="md">{markdown(topic, text)}</div></details></section>'


def section_claims(topic: Topic) -> str:
    if not topic.ledger:
        return ""
    contested = {item["claim"]: item for item in (topic.judgement or {}).get("contested", [])}
    rows = []
    for claim_id, claim in sorted(topic.claims.items(), key=lambda item: int(item[0][1:])):
        judged = topic.verdicts.get(claim_id, {})
        verdict = judged.get("verdict", "not judged")
        source = topic.sources.get(claim.get("source"), {})
        quote = f'<blockquote>{esc(claim.get("quote", ""))}</blockquote>' if claim.get("quote") else ""
        checked = "" if claim.get("quoteVerified") else ' <span class="hint">quote not found on the stored page</span>'
        reason = f'<p class="hint">{linked_refs(topic, esc(judged["reason"]))}</p>' if judged.get("reason") else ""
        flag = ' <span class="badge verdict-weakened">contested</span>' if claim_id in contested else ""
        source_html = (f'{esc(source.get("id", ""))} {link(source.get("url"), source.get("title") or source.get("url") or "")} '
                       f'<span class="hint">{esc(source.get("evidenceType", ""))}, reliability {esc(source.get("reliability", "?"))}'
                       + (f', {esc(source["published"])}' if source.get("published") else "") + "</span>")
        rows.append(f'<tr id="{esc(claim_id)}" data-verdict="{esc(verdict)}"><td class="cid">{esc(claim_id)}</td>'
                    f'<td>{esc(claim["text"])}{flag}<details><summary>Quote and source</summary>{quote}{checked}<p>{source_html}</p>{reason}</details></td>'
                    f'<td>{badge("verdict", verdict)}' + (f'<br><span class="hint">credibility {esc(judged["credibility"])}</span>' if judged.get("credibility") else "")
                    + f'</td><td>{esc(", ".join(claim.get("questions", [])))}</td></tr>')
    options = "".join(f'<option value="{esc(verdict)}">{esc(verdict)}</option>' for verdict in (*research.CLAIM_VERDICTS, "not judged"))
    return (f'<section id="claims"><h2>Claims</h2><p class="hint">Every claim quotes a stored page. Credibility runs from 1 '
            f'(confirmed by other sources) to 6 (cannot be judged).</p>'
            f'<div class="filters"><input type="search" id="claim-filter" placeholder="Filter claims" aria-label="Filter claims">'
            f'<select id="verdict-filter" aria-label="Verdict"><option value="">All verdicts</option>{options}</select></div>'
            f'<div class="scroll"><table class="claims"><thead><tr><th>ID</th><th>Claim</th><th>Verdict</th><th>Q</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')


def section_sources(topic: Topic) -> str:
    if not topic.sources:
        return ""
    used: dict[str, int] = {}
    for claim in topic.claims.values():
        used[claim.get("source", "")] = used.get(claim.get("source", ""), 0) + 1
    items = "".join(f'<li id="{esc(source_id)}"><b>{esc(source_id)}</b> {link(source.get("url"), source.get("title") or source.get("url") or "")} '
                    f'<span class="hint">{esc(source.get("evidenceType", ""))}, reliability {esc(source.get("reliability", "?"))}'
                    + (f', {esc(source["published"])}' if source.get("published") else "")
                    + f', {used.get(source_id, 0)} claim{"s" if used.get(source_id, 0) != 1 else ""}</span></li>'
                    for source_id, source in sorted(topic.sources.items(), key=lambda item: int(re.sub(r"\D", "", item[0]) or 0)))
    return f'<section id="sources"><details><summary><h2>Sources ({len(topic.sources)})</h2></summary><ol class="sources">{items}</ol></details></section>'


def section_history(topic: Topic) -> str:
    if not topic.watch:
        return ""
    watch = topic.watch
    facts = (f'<p>Checked {esc(watch.get("cadence", ""))} (every {esc(watch.get("cadenceDays", ""))} days). Last checked '
             f'{esc(watch.get("lastChecked", ""))}, last changed {esc(watch.get("lastChanged", ""))}. '
             f'Retire when: {esc(watch.get("retireWhen", ""))}</p>')
    deltas = []
    for path in sorted((topic.dir / "delta").glob("*.json"), reverse=True):
        if path.stem.endswith("-searches"):
            continue
        delta = json.loads(path.read_text(encoding="utf-8"))
        deltas.append(f'<li><b>{esc(delta.get("stamp", path.stem))}</b> {badge("change", "material" if delta.get("material") else "no material change")} '
                      f'{esc(delta.get("summary", ""))}</li>')
    log = "".join(f'<li>{esc(item.get("date"))}: {esc(item.get("kind"))}, version {esc(item.get("version"))}</li>' for item in reversed(watch.get("log", [])))
    return (f'<section id="history"><h2>Living topic</h2>{facts}'
            + (f'<h3>Refreshes</h3><ul>{"".join(deltas)}</ul>' if deltas else "")
            + f'<details><summary>Run log</summary><ul>{log}</ul></details></section>')


# The page -------------------------------------------------------------------------------------------------

STYLE = """
:root{--bg:#fbfaf8;--panel:#ffffff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e4e2dd;--accent:#2f5d8a;
--ok:#2e7d4f;--weak:#b7791f;--bad:#b42318;--none:#8a8a8f;--c:#d7eedf;--i:#f8d9d5;--n:#ecebe8;
--adopt:#2e7d4f;--trial:#2f5d8a;--assess:#b7791f;--hold:#8a8a8f;--bar:#9db7d0;--in:#2e7d4f;--out:#d9a29b}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141416;--panel:#1d1d20;--ink:#ecebe8;--muted:#a1a1a8;
--line:#2f2f34;--accent:#8db7e0;--ok:#6cc58f;--weak:#e0b25a;--bad:#f08a80;--none:#8a8a8f;--c:#1f3d2b;--i:#4a2522;--n:#2a2a2e;
--adopt:#6cc58f;--trial:#8db7e0;--assess:#e0b25a;--hold:#8a8a8f;--bar:#4f6f8f;--in:#6cc58f;--out:#9a5a52}}
:root[data-theme="dark"]{--bg:#141416;--panel:#1d1d20;--ink:#ecebe8;--muted:#a1a1a8;--line:#2f2f34;--accent:#8db7e0;--ok:#6cc58f;
--weak:#e0b25a;--bad:#f08a80;--none:#8a8a8f;--c:#1f3d2b;--i:#4a2522;--n:#2a2a2e;--adopt:#6cc58f;--trial:#8db7e0;--assess:#e0b25a;
--hold:#8a8a8f;--bar:#4f6f8f;--in:#6cc58f;--out:#9a5a52}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI","Hiragino Sans","Yu Gothic UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.75rem;line-height:1.25;margin:.2em 0}
h2{font-size:1.3rem;margin:0 0 .6em}
h3{font-size:1.05rem;margin:.2em 0 .5em}
h4{font-size:.95rem;margin:1em 0 .4em;color:var(--muted)}
a{color:var(--accent)}
section{margin:28px 0;padding:20px;background:var(--panel);border:1px solid var(--line);border-radius:12px}
.top{margin:8px 0 20px}.crumbs{margin:0;color:var(--muted);font-size:.9rem}.meta{margin:.2em 0;color:var(--muted);font-size:.9rem}
nav.toc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.9rem;margin-bottom:8px}
.lead{border-left:4px solid var(--accent)}
.hint{color:var(--muted);font-size:.85rem}.missing{color:var(--muted);font-style:italic}.note{font-size:.92rem}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.75rem;font-weight:600;border:1px solid currentColor;white-space:nowrap;vertical-align:middle}
.ring-adopt{color:var(--adopt)}.ring-trial{color:var(--trial)}.ring-assess{color:var(--assess)}.ring-hold,.ring-not-applied{color:var(--hold)}
.verdict-survives,.verdict-holds,.verdict-sound{color:var(--ok)}.verdict-weakened,.verdict-weak{color:var(--weak)}
.verdict-falls,.verdict-refuted,.verdict-unsupported{color:var(--bad)}.verdict-not-judged{color:var(--none)}
.certainty-high{color:var(--ok)}.certainty-moderate{color:var(--trial)}.certainty-low{color:var(--weak)}.certainty-very-low{color:var(--bad)}
.effort-effort-s,.effort-effort-m,.effort-effort-l,.status-living,.status-accepted,.status-draft,.status-paused,.status-retired,.change-no-material-change{color:var(--muted)}
.change-material{color:var(--weak)}
.cards{display:grid;gap:14px}
.card{border:1px solid var(--line);border-left:4px solid var(--hold);border-radius:10px;padding:14px 16px}
.card.ring-adopt{border-left-color:var(--adopt)}.card.ring-trial{border-left-color:var(--trial)}.card.ring-assess{border-left-color:var(--assess)}
.card{color:inherit}
.card-head{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px}.card-head h3{margin:0;flex:1 1 220px}
.idea-id{font-weight:700;color:var(--muted)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;margin:10px 0 0}dt{color:var(--muted);font-size:.85rem;padding-top:2px}dd{margin:0}
@media (max-width:600px){dl{grid-template-columns:1fr}dt{padding-top:6px}section{padding:14px 12px}td,th{padding:6px 5px}}
.leading{margin:.5em 0;padding-left:1.1em}.leading li{margin:.2em 0}
.trail{font-size:.85rem;color:var(--muted);margin:.5em 0 0}
.answer{padding:10px 0;border-top:1px solid var(--line)}.answer:first-of-type{border-top:0}.q{margin:0 0 .3em}
.down{color:var(--bad);font-weight:600;font-size:.85rem}.up{color:var(--ok);font-weight:600;font-size:.85rem}
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.panel{min-width:0}
.bars{display:grid;gap:5px}.bar-row{display:grid;grid-template-columns:minmax(0,13em) 1fr 3.2em;gap:8px;align-items:center;font-size:.85rem}
.bar-label{overflow-wrap:anywhere;line-height:1.3}.bar-track{background:var(--n);border-radius:4px;height:12px}
.bar{display:block;height:12px;border-radius:4px;background:var(--bar)}.bar-count{text-align:right;font-variant-numeric:tabular-nums}
.b-in{background:var(--in)}.b-out{background:var(--out)}.b-muted{background:var(--none)}
.g-a,.g-b{background:var(--ok)}.g-c{background:var(--bar)}.g-d,.g-e{background:var(--weak)}.g-f{background:var(--bad)}
.stack{display:flex;height:16px;border-radius:6px;overflow:hidden;background:var(--n)}.seg{display:block;height:100%}
.v-holds{background:var(--ok)}.v-weak{background:var(--weak)}.v-refuted{background:var(--bad)}.v-unsupported{background:#c06a5f}.v-not-judged{background:var(--none)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:.8rem;margin:6px 0 10px;color:var(--muted)}
.key{display:inline-flex;align-items:center;gap:5px}.dot{width:10px;height:10px;border-radius:3px;display:inline-block}
.dot.r-c{background:var(--c)}.dot.r-i{background:var(--i)}.dot.r-n{background:var(--n)}
.question{padding:12px 0;border-top:1px solid var(--line)}.question:first-of-type{border-top:0}
.ranking{margin:.3em 0 .4em;padding-left:1.4em}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
table.ach td{text-align:center;font-weight:700;width:3.2em}.r-c{background:var(--c)}.r-i{background:var(--i)}.r-n{background:var(--n)}
table.ach th[scope=row]{font-weight:400}.claim-text{display:block;color:var(--muted);font-size:.82rem;max-width:46em}
tr.out th,tr.out td{opacity:.45}tr.out .claim-text{text-decoration:line-through}
.assumptions li{margin:.3em 0}
a.cref{text-decoration:none;font-size:.85em;font-variant-numeric:tabular-nums}
a.cref.cv-refuted,a.cref.cv-unsupported{color:var(--bad);text-decoration:line-through}
.md :is(h2){font-size:1.15rem;margin-top:1.4em}.md p,.md li{max-width:72ch}
details>summary{cursor:pointer;color:var(--accent);font-size:.9rem}details>summary h2{display:inline;color:var(--ink);font-size:1.3rem}
blockquote{margin:.5em 0;padding:.3em .8em;border-left:3px solid var(--line);color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.filters input,.filters select{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
.filters input{flex:1 1 200px}
td.cid{font-weight:700;white-space:nowrap}
.sources li{margin:.3em 0;overflow-wrap:anywhere}
footer{color:var(--muted);font-size:.8rem;text-align:center}
@media print{section{break-inside:avoid-page;border:0}details{display:block}details>*{display:block}.filters{display:none}}
"""

SCRIPT = """
(function(){var q=document.getElementById('claim-filter'),v=document.getElementById('verdict-filter');if(!q)return;
function f(){var t=q.value.toLowerCase(),w=v.value;document.querySelectorAll('table.claims tbody tr').forEach(function(r){
var ok=(!w||r.dataset.verdict===w)&&(!t||r.textContent.toLowerCase().indexOf(t)>=0);r.style.display=ok?'':'none';});}
q.addEventListener('input',f);v.addEventListener('change',f);
document.addEventListener('click',function(e){var a=e.target.closest('a.cref');if(!a)return;var r=document.getElementById(a.getAttribute('href').slice(1));
if(r){q.value='';v.value='';f();var d=r.querySelector('details');if(d)d.open=true;}});})();
"""


def page(title: str, body: str, script: bool = True) -> str:
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{esc(title)}</title><style>{STYLE}</style></head><body><main>{body}</main>"
            + (f"<script>{SCRIPT}</script>" if script else "") + "</body></html>\n")


def render_topic(root: Path, topic_id: str, dashboard: bool = False) -> str:
    """A topic's page; with dashboard, it links back to the use case's dashboard (index.html) beside it."""
    topic = Topic(root, topic_id)
    toc = [("bottom-line", "Bottom line"), ("ideas", "Ideas"), ("answers", "Certainty"), ("evidence", "Evidence"),
           ("hypotheses", "Hypotheses"), ("report", "Full report"), ("claims", "Claims"), ("sources", "Sources"), ("history", "History")]
    body = [section_bottom_line(topic), section_ideas(topic), section_answers(topic), section_evidence(topic),
            section_hypotheses(topic), section_report(topic), section_claims(topic), section_sources(topic), section_history(topic)]
    present = [(anchor, name) for anchor, name in toc if any(f'id="{anchor}"' in part for part in body)]
    back = '<a href="index.html">&larr; All topics</a>' if dashboard else ""
    nav = '<nav class="toc">' + back + "".join(f'<a href="#{anchor}">{name}</a>' for anchor, name in present) + "</nav>"
    return page(topic.title, section_header(topic) + nav + "".join(body)
                + f"<footer>Research Center report for topic {esc(topic.id)}. Built from the topic's committed outputs; "
                  "every statement traces to a claim and its stored source.</footer>")


# The dashboard --------------------------------------------------------------------------------------------

DASHBOARD = "index"  # the dashboard's file name; a topic of that name would collide with it
STATUS_ORDER = {status: index for index, status in enumerate(("living", "accepted", "paused", "draft", "retired"))}


def topic_ids(root: Path) -> list[str]:
    return sorted(path.parent.name for path in (root / "research").glob("*/brief.md"))


def progress(topic: Topic) -> str:
    """How far the pipeline got: the last stage with its outputs, or done."""
    done = [stage for stage in research.STAGES if research.stage_done(topic.dir, stage)]
    if not done:
        return "not run"
    return "done" if done[-1] == research.STAGES[-1] else f"{done[-1]} done"


def topic_card(topic: Topic) -> str:
    rows = idea_rows(topic)
    rings = {ring: sum(row["fit"].get("ring") == ring for row in rows) for ring in research.RINGS}
    ring_html = "".join(f'<span class="badge ring-{ring.lower()}">{count} {ring}</span>' for ring, count in rings.items() if count)
    leading = [row for row in rows if row["fit"].get("ring") in ("ADOPT", "TRIAL")][:3]
    leading_html = "".join(f'<li>{badge("ring", row["fit"]["ring"])} {esc(row["name"])}'
                           + (f' <span class="hint">{esc(row["judged"]["verdict"].lower())}</span>' if row["judged"].get("verdict") else "")
                           + "</li>" for row in leading)
    answers = {item["question"]: item["certainty"] for item in (topic.judgement or {}).get("answers", [])}
    certainty = "".join(f'<span class="key"><b>{esc(question)}</b> {badge("certainty", answers[question])}</span>'
                        for question in topic.questions if question in answers)
    watch = topic.watch or {}
    facts = [f"{len(topic.questions)} question{'s' if len(topic.questions) != 1 else ''}"]
    if topic.ledger:
        facts.append(f"{len(topic.claims)} claims, {len(topic.sources)} sources")
    if watch.get("lastChecked"):
        facts.append(f"checked {watch['lastChecked']}, changed {watch.get('lastChanged', '?')}")
    state = progress(topic)
    ring = leading[0]["fit"]["ring"] if leading else "none"
    return (f'<article class="card ring-{esc(ring.lower())}">'
            f'<div class="card-head"><h3><a href="{esc(topic.id)}.html">{esc(topic.title)}</a></h3>{badge("status", topic.status)}'
            + (badge("change", state) if state != "done" else "") + "</div>"
            + f'<p class="hint">{esc(topic.id)} · {esc(" · ".join(facts))}</p>'
            + (f'<div class="legend">{ring_html}</div>' if ring_html else "")
            + (f'<ul class="leading">{leading_html}</ul>' if leading_html else "")
            + (f'<div class="legend">Certainty {certainty}</div>' if certainty else "") + "</article>")


def scope_line(root: Path) -> str:
    """The use case's scope status and the first paragraph of whom it serves, without its evidence paths."""
    scope = read(root, "scope.md")
    if not scope:
        return ""
    status = re.search(r"^Status:\s*(\S+)", scope, re.MULTILINE)
    who = research.sections(scope).get("Who", "").strip().split("\n\n")[0]
    who = re.sub(r"\s*\[[^\]]*\]", "", who)  # evidence paths mean nothing outside the repository
    return (f'<p class="meta">Scope {badge("status", status.group(1) if status else "unknown")}</p>'
            + (f'<div class="md">{MARKDOWN.render(who)}</div>' if who else ""))


def render_dashboard(root: Path) -> str:
    topics = [Topic(root, topic_id) for topic_id in topic_ids(root)]
    topics.sort(key=lambda topic: (STATUS_ORDER.get(topic.status, len(STATUS_ORDER)), topic.id))
    usecase = load(root, "usecase.json") or {}
    title = usecase.get("title") or rc.settings(root).get("name") or "Research"
    cards = "".join(topic_card(topic) for topic in topics) or '<p class="missing">No research topics yet.</p>'
    living = sum(topic.status == "living" for topic in topics)
    summary = f"{len(topics)} topic{'s' if len(topics) != 1 else ''}, {living} living"
    return page(title, f'<header class="top"><p class="crumbs">Research Center</p><h1>{esc(title)}</h1>'
                f'<p class="meta">{esc(summary)}</p>{scope_line(root)}</header>'
                f'<section id="topics"><h2>Topics</h2><div class="cards">{cards}</div></section>'
                "<footer>Built from the committed research outputs. Open a topic for its evidence.</footer>", script=False)


def output_path(root: Path, name: str) -> Path:
    return root / ".rc-local" / "reports" / f"{name}.html"


def write_page(path: Path, text: str) -> Path:
    found = rc.write_text(path, text)
    if found:
        print(f"redacted {len(found)} secret(s) from {path.name}")
    return path


def command_topic(root: Path, topic: str, output: Path | None) -> Path:
    return write_page(output or output_path(root, topic), render_topic(root, topic))


SHARES = "shares.json"  # beside the pages: the artifact link each page was shared at, so an update keeps the link


def shares(folder: Path) -> dict[str, Any]:
    return load(folder, SHARES) or {}


def remember_share(folder: Path, name: str, url: str) -> None:
    """Record where a page was shared (a claude.ai artifact link), so the next share updates it in place."""
    if not re.fullmatch(r"https://claude\.ai/\S+", url):
        raise rc.RcError(f"not a claude.ai artifact link: {url}")
    rc.write_json(folder / SHARES, {**shares(folder), name: {"url": url, "sharedAt": rc.today()}})


def manifest(root: Path, topic: str | None, page_path: Path) -> dict[str, Any]:
    """What a share publishes: the page, the pages beside it (for the dashboard), its title, and the link it was
    shared at before, if any."""
    folder, name = page_path.parent, topic or DASHBOARD
    beside = {} if topic else {f"{other}.html": str(folder / f"{other}.html") for other in topic_ids(root)}
    title = Topic(root, topic).title if topic else (load(root, "usecase.json") or {}).get("title") or rc.settings(root).get("name")
    return {"page": str(page_path), "files": beside, "title": title, "sharedAt": shares(folder).get(name)}


def command_dashboard(root: Path, output: Path | None) -> Path:
    """The dashboard and every topic's page beside it, linked both ways: one folder that can be shared whole."""
    ids = topic_ids(root)
    if DASHBOARD in ids:
        raise rc.RcError(f"a topic named {DASHBOARD} collides with the dashboard page; rename the topic")
    folder = output or output_path(root, DASHBOARD).parent
    for topic in ids:
        write_page(folder / f"{topic}.html", render_topic(root, topic, dashboard=True))
    return write_page(folder / f"{DASHBOARD}.html", render_dashboard(root))


def main() -> int:
    parser = argparse.ArgumentParser(prog="./rc report", description="Render research as self-contained HTML pages")
    parser.add_argument("root", type=Path)
    parser.add_argument("topic", nargs="?", help="one topic's page; without it, the dashboard and every topic's page")
    parser.add_argument("--output", type=Path, help="the page (with a topic) or the folder (without); default .rc-local/reports/")
    parser.add_argument("--manifest", action="store_true", help="after writing, print what a share publishes, as JSON")
    parser.add_argument("--shared-at", metavar="URL", help="record the artifact link the page was shared at; writes no page")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.shared_at:
            folder = (args.output.parent if args.topic else args.output) if args.output else output_path(root, DASHBOARD).parent
            remember_share(folder, args.topic or DASHBOARD, args.shared_at)
            print(f"recorded: {args.topic or 'the dashboard'} is shared at {args.shared_at}")
            return 0
        path = command_topic(root, args.topic, args.output) if args.topic else command_dashboard(root, args.output)
        if args.manifest:
            print(json.dumps(manifest(root, args.topic, path), ensure_ascii=False, indent=2))
            return 0
    except (rc.RcError, OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
