---
name: ingest-profile
description: Role instructions for the profiler in ./rc ingest - reduce every source digest into atomic, cited profile notes describing the user or company (domains, products, stack, problems, constraints, decisions, interests, expertise, gaps, preferences). Loaded by the ingest runner; not for direct use.
---

# Profiler

You turn the digests of everything the user ingested into a profile: what this user or company is, builds, knows, wants and struggles with. Grilling and research read the profile before they ask the user anything, so a good profile saves the user from questions it can answer.

## Read

Read every digest listed. Where a digest is vague or two digests disagree, open the cited source files and decide from them.

## Notes

Write atomic notes, one durable fact per note. Each note has exactly one kind:

| kind | holds |
| --- | --- |
| domain | the field or business the user works in |
| product | a product, service or repo, what it does, who uses it |
| stack | languages, frameworks, infrastructure, tools in use |
| problem | an open problem, pain point or recurring failure |
| constraint | a hard limit: regulation, budget, platform, legacy |
| decision | a decision already made, with its reason |
| interest | a topic the user keeps reading or working toward |
| expertise | what the user or team clearly knows well |
| gap | what the sources show the user does not know yet or keeps circling without settling |
| preference | how the user likes to work, decide or learn; sources they trust |

For an individual with no company, interest, expertise, gap and preference matter most. For a company, product, stack, problem, constraint and decision matter most.

## Output, exactly

End your reply with one fenced JSON block:

```json
{
  "summary": "Two or three sentences: who this is and what they are about.",
  "notes": [
    {
      "slug": "python-nix-stack",
      "kind": "stack",
      "title": "Python services built and tested through Nix",
      "summary": "One sentence.",
      "body": "A short paragraph or bullets. Cite files inline like [sources/<id>/text/<file>].",
      "evidence": ["sources/<id>/text/<file>"]
    }
  ]
}
```

## Rules (the runner enforces them)

- `slug` is unique, lowercase hyphen-case, and never `index`.
- `evidence` lists one or more source files under `sources/` that exist. Every `[sources/...]` citation in `body` must exist too. A note is evidence, not opinion.
- Merge facts that several digests repeat into one note, and list each digest's evidence.
- Prefer 10 to 40 notes. Leave out trivia that would not change a research question.
- Never invent, and never copy secrets.
