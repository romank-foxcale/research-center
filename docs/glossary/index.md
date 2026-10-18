---
id: glossary.index
title: Glossary
status: active
summary: Terms of the Research Center - profile, licence rule, scope, instance, source, digest, profile, brief, claim, ledger, verdict, contested, fit ring, adapter, pack, record, evidence type, hypothesis, exclusion criterion, candidate, snowballing, screening flow, living topic, refresh, delta, reliability, credibility, certainty, drifted, competing hypotheses matrix, diagnostic claim, key assumption, assessment, handoff.
verified_at: 2026-10-11
evidence:
  - scripts/research/research.py
  - scripts/ingest/ingest.py
relations:
  - docs/architecture/research-center.md
---

# Glossary

- **Profile**: whom the RC works for, a company or a person (profiles/&lt;id&gt;/): name, description, type and interest tags in profile.json, with its own sources, profile notes and research; config is shared by the instance. Formerly a use case.
- **Licence rule**: a company profile may use only permissive licences (templates/licences.json), a personal one any; the runner classifies every licence and flags the unusable ones.
- **Scope**: a profile's optional scope.md: whom it serves, products and plug-in points, hard constraints, how value is measured, out of scope, scouting lens, source preferences.
- **Report page**: a topic's results as one self-contained HTML page (`rc report <topic>`), computed from its committed outputs; the **dashboard** (`rc report`) lists a profile's topics with their pages beside it. Shared as private artifacts with the rc-share skill.
- **Instance**: a private repo made from the template with `./rc bootstrap install`. Only an instance holds data.
- **Source**: something ingested (folder, git, url, notion, gdrive), described in catalog/sources/&lt;id&gt;.json and stored as text in sources/&lt;id&gt;/.
- **Digest**: one source's key facts, open problems and terms, every bullet cited.
- **Profile**: atomic notes about the user or company, reduced from all digests, each with evidence.
- **Brief**: the accepted definition of a research topic: questions Q1..Qn, scope, needs, success criteria, source preferences.
- **Claim**: one checkable statement from a web page, with a verbatim quote. It is quote-verified when the quote is found in the stored page.
- **Ledger**: research/&lt;topic&gt;/claims.json and claims.md: every source and claim of a run.
- **Verdict**: HOLDS, WEAK, REFUTED or UNSUPPORTED for a claim; SURVIVES, WEAKENED or FALLS for an idea.
- **Contested**: a claim a reviewer refuted and the judge kept. Only the user settles it.
- **Fit ring**: ADOPT, TRIAL, ASSESS or HOLD: how an idea fits the user's repos and needs.
- **Adapter**: a runner-side search over one kind of source (scholarly works, news, books, a feed, a watched page), described in catalog/adapters/&lt;id&gt;.json.
- **Pack**: a set of domain adapters (medicine: pubmed; software: github) an instance enables with ./rc sources enable &lt;pack&gt;.
- **Record**: one adapter result: title, authors, date, URL, DOI, evidence type, abstract; keyed by DOI, else canonical URL.
- **Evidence type**: what kind of evidence a record is (peer-reviewed, preprint, journalism, regulation, book, ...), independent of the subject.
- **Hypothesis**: an answer the planner expects (H1..). Each one gets at least one disconfirming search.
- **Exclusion criterion**: a numbered reason (X1..) taken from the brief for which the screener drops a record; X0 is "bears on no question".
- **Candidate**: a record the adapter searches found (R1..), before screening. **Included** candidates are stored and read by the researchers.
- **Snowballing**: following the references (backward) and the citing works (forward) of the key included records, one hop per research.snowballDepth, each hop screened again.
- **Screening flow**: identified, duplicates, screened, excluded by criterion, included (PRISMA-style), shown in screening.md and the report.
- **Living topic**: a topic whose brief has a cadence; refreshed with ./rc research refresh, versioned, its searches saved in watch.json.
- **Refresh**: re-running a living topic's saved searches since the last check, screening only new records, collecting claims from them with the next ids, and re-deriving the conclusions when new verified evidence arrived.
- **Delta**: research/&lt;topic&gt;/delta/&lt;date&gt;.md, what one refresh changed; its Needs your review section lists flipped verdicts, moved rings and newly contested claims.
- **Reliability**: how trustworthy a source is, A completely reliable to E unreliable, F cannot be judged; capped by its evidence type.
- **Credibility**: how believable one claim is, 1 confirmed to 5 improbable, 6 cannot be judged; given by the judge.
- **Certainty**: how sure an answer is, high, moderate, low or very low: high minus the named downgrades (reliability, inconsistency, indirectness, imprecision, one-sided), plus any upgrades.
- **Drifted**: a claim whose page, re-fetched after its evidence type's half-life, no longer contains the quote or is gone.
- **Competing hypotheses matrix**: per question with two or more plan hypotheses, every relied-on claim rated consistent (C), inconsistent (I) or neutral (N) with each; hypotheses rank by surviving inconsistent evidence.
- **Diagnostic claim**: a claim rated differently across the hypotheses, so it tells them apart.
- **Key assumption**: something an answer rests on that the evidence does not show (A1..); sceptics and the judge rule on it.
- **Assessment**: a report paragraph that is the writer's judgement beyond the cited evidence, marked as such.
- **Handoff**: a Control Center task plan for ADOPT and TRIAL ideas.
