---
name: rc-research
description: Run, resume, follow and present a Research Center research run with ./rc research - plan sources, search the adapters, screen the results, collect from them and the web, analyze, critique by anonymous sceptics, judge, apply to the user's repos and report - then walk the user through the report, its caveats and the Control Center handoff. Use when the user wants to run or resume research on an accepted brief, asks how a research run is going, or wants the report explained, questioned or compared.
---

# Run and present research

## Run

1. Check the brief is accepted: `./rc research show <topic>`. If it is not, use grill-research-topic first.
2. Start `./rc research run <topic>` in the background, then follow it with `./rc watch`. Relay each stage, what agents say, stalls, warnings (rejected replies, dropped citations) and the result as they happen. Never leave the user blind during a run.
3. On a stop:
   - **Budget reached** (`budget.researchCalls`): finished stages are kept, and the next run resumes at the first missing output. Ask before passing a bigger `--budget`.
   - **Provider logged out or a CLI error**: tell the user which login to fix (`./rc doctor`). The RC never falls back to another model.
   - **Redo a stage**, for example after editing the brief or swapping a model: `--from <stage>`. It clears that stage and every later one.

## Present

Read research/<topic>/report.md, judgement.md and fit.md, then give the user:

- the TL;DR and the answer to each question, citing claim ids;
- how the sources were found: the screening flow at the end of the report (identified, duplicates, excluded by criterion, included). Point at research/<topic>/screening.md when the user doubts an exclusion, and at searches.json for the exact queries;
- what the sceptics and the judge struck down (the report's "Refuted or unsupported" section), and any **contested** claims, which only the user can settle;
- the fit: ADOPT, TRIAL, ASSESS or HOLD per idea, and where it lands in their repos;
- the handoff: if research/<topic>/handoff.md exists, it is a Control Center task plan. The user copies it into the CC's `plans/active/` and refines it there with grill-task-planning. The RC never writes into a CC or into product code.

## Answering follow-up questions

Answer from the ledger (claims.md), the stored pages under sources/ and the profile, citing claim ids and paths. When the evidence does not cover a question, say so, and offer a new topic, or re-running collect after adding a question to the brief.

## Rules

- Commit research/ and sources/ only when the user asks, after `./rc validate`.
- Don't edit the generated outputs by hand. Change the brief or a role, then re-run from the right stage.
