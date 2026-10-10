---
id: glossary.index
title: Glossary
status: active
summary: Terms of the Research Center - instance, source, digest, profile, brief, claim, ledger, verdict, contested, fit ring, adapter, record, evidence type, hypothesis, exclusion criterion, candidate, snowballing, screening flow, handoff.
verified_at: 2026-10-11
evidence:
  - scripts/research/research.py
  - scripts/ingest/ingest.py
relations:
  - docs/architecture/research-center.md
---

# Glossary

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
- **Record**: one adapter result: title, authors, date, URL, DOI, evidence type, abstract; keyed by DOI, else canonical URL.
- **Evidence type**: what kind of evidence a record is (peer-reviewed, preprint, journalism, regulation, book, ...), independent of the subject.
- **Hypothesis**: an answer the planner expects (H1..). Each one gets at least one disconfirming search.
- **Exclusion criterion**: a numbered reason (X1..) taken from the brief for which the screener drops a record; X0 is "bears on no question".
- **Candidate**: a record the adapter searches found (R1..), before screening. **Included** candidates are stored and read by the researchers.
- **Snowballing**: following the references (backward) and the citing works (forward) of the key included records, one hop per research.snowballDepth, each hop screened again.
- **Screening flow**: identified, duplicates, screened, excluded by criterion, included (PRISMA-style), shown in screening.md and the report.
- **Handoff**: a Control Center task plan for ADOPT and TRIAL ideas.
