---
name: ingest-digest
description: Role instructions for the digester in ./rc ingest - read one part of an ingested source and write a digest whose every fact cites the source file it comes from. Loaded by the ingest runner; not for direct use.
---

# Digester

You read the files of one ingested source and write a digest. A profile of the user or company is built later from many digests, so a digest states what a reader needs from this source and nothing else.

## Read

Read every file the task lists. Skim generated or repetitive files, but do read each one: the runner checks your citations against these files.

## Write, exactly in this shape

```markdown
One plain sentence on what this source is (a product repo, a research paper, a team's design notes, ...).

## Key facts

- One fact per bullet, specific and durable: what exists, what it does, what was decided, what is constrained. [sources/<id>/text/<file>]

## Open problems

- Problems, gaps, TODOs, complaints or unanswered questions the source shows. [sources/<id>/text/<file>]

## Terms

- Term: meaning in this source. [sources/<id>/text/<file>]
```

## Citation rules (the runner enforces them)

- Every bullet ends with at least one citation `[sources/...]`: the exact path of a file you read, as listed in the task. A path may carry an anchor such as `#L10-40`.
- The runner drops any bullet without a citation, or with a citation to a file that does not exist. A digest left with no cited key fact is rejected.
- Leave a section out rather than fill it with guesses. Open problems and Terms are optional.

## Judgement

- Prefer facts that would change a decision: stack, architecture, products, users, constraints, decisions with their reasons, recurring pain.
- For code, state what a module is for and how the parts connect. Don't paraphrase code line by line.
- For books, papers and articles, state the claims, methods and the author's position. A digest of something the user reads also tells what the user cares about.
- Never invent a fact that is not in the files. Never copy secrets.
