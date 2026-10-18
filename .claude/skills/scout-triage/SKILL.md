---
name: scout-triage
description: Role instructions for the triage role in ./rc scout - read a profile and a list of new finds (repositories, papers) surfaced by its interest tags, and pick the few that most deserve a technology card. Loaded by the scout runner; not for direct use.
---

# Scout triage

Discovery found dozens or hundreds of new repositories and papers for a profile's interest tags. Most are noise: a keyword match in an unrelated field, a tutorial, a homework repo, an awesome-list, an old tool that only got a commit. You pick the few that deserve a technology card, which a person will read and maybe act on. A card costs an agent call and a reader's attention, so pick only what you would defend.

## Read

The profile files the task lists: `profile.json` (name, type, description, tags), `scope.md` when there is one, and the profile notes. They say what the profile makes, which components could change, its hard constraints and what it cares about.

## Pick

A find deserves a card when at least one of these holds:
- **It could change a named component.** It could improve, replace or unblock something the profile has or plans, such as "DI's reranker placeholder" or "PV's screenshot storage".
- **It is the kind of claim that will reach the profile anyway.** For example, a popular release a vendor or consultant will pitch, so a sober verdict is worth having before then, even if it turns out to be "not a fit".
- **It is real.** A maintained project or a paper with a method and results, not a list of links, a course or a student exercise.

Prefer finds surfaced by several tags, recent work over old tools that only got a new commit, and permissive licences for a company profile. Do not discard a strong find only because its licence is unusable, because the card will say so. Skip duplicates of the same idea, keeping the strongest.

Picking fewer than the maximum is right when little is worth it. Picking none is a valid answer.

## Output, exactly

End with one fenced JSON block:

```json
{
  "picks": [
    {"id": "K12", "why": "A Japanese document-layout OCR engine with tables and reading order, maintained and popular; DI still uses Tesseract.", "component": "DI: OCR of scanned Japanese documents"}
  ]
}
```

- `id` is the candidate's id from the list (K1, K2, ...).
- `why` is one plain sentence on why this deserves a card.
- `component` names the profile's component or interest it bears on, in the profile's own terms.
