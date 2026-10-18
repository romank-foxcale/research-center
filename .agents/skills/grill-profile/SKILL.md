---
name: grill-profile
description: Create or change a profile in the Research Center - whom it scouts and researches for (a company, a product line, a person) - with its name, type (company or personal, which sets the licence rule), description and interest tags, grilling the user evidence-first; optionally write its longer scope.md. Use when the user wants a new profile, to describe or retype one, to add, edit, remove or propose its interest tags, or to write or review its scope.
---

# Grill a profile

A profile is whom the RC works for: `profiles/<id>/`, with its own sources, profile notes, research and scouting. Everything the RC finds is judged against it, so ground it in evidence and keep it short.

## 1. Create it

`./rc profile new <id> --name "<name>" --type company|personal --description "<one or two sentences>"`. Ids are lowercase hyphen-case: `foxcale`, `personal`.

The type matters, and you ask it outright:
- **company**: something that makes money from what it builds. Only permissive licences (MIT, Apache-2.0, BSD and similar, `templates/licences.json`) are usable, and every other licence is flagged.
- **personal**: learning and non-commercial use. Any licence is usable.

## 2. Gather evidence before asking

Read what already describes the subject, and state it back instead of asking:

- The profile notes (`profiles/<id>/knowledge/profile/index.md`), when material was ingested (rc-ingest, `./rc -p <id>`).
- Material the user points at or drops into `profiles/<id>/inbox/`: a website, product repos or their Control Centers, specs. Never copy secrets. If you find credentials, tell the user where, without quoting them.

## 3. Describe it

The description is one to three plain sentences: who they are, what they make or want, and the constraint that matters most. Edit it with `./rc profile edit <id> --description "..."`.

## 4. Interest tags

Tags are what the scout searches for every week, so they decide what the profile hears about.

- **From the user:** `./rc -p <id> tags add "<tag>" --why "<one sentence>"`, and `tags rename <old> <new>` or `tags remove <tag>` to change them.
- **From the material:** the user drops files into `profiles/<id>/inbox/`, and `./rc -p <id> ingest run` registers and digests them (rc-ingest). Then `./rc -p <id> tags suggest` has the tagger propose tags, each with a reason and the files it rests on, at one or two agent calls.
- **Review with the user:** show each proposal with its reason. Accept with `tags accept <tag>...` (or `--all`), reject with `tags reject <tag>...`; a rejected tag is never proposed again. Offer to rename a proposal that is close but not right.
- **A good tag** is two to four searchable words tied to something the profile has or wants: "Japanese OCR", "technology-assisted review". Push back on tags like "AI" that would flood the scout.

## 5. The longer scope, only when it helps

A company with products and hard constraints benefits from `scope.md`. `./rc profile scope <id>` starts it from the template, with these sections:
- who;
- products and the components a new technology could plug into;
- hard constraints;
- how value is measured;
- out of scope;
- scouting lens;
- source preferences.

Put each fact's source in brackets after it. Show it to the user, change it until they agree, then `./rc profile accept <id>`. A personal profile rarely needs one.

## Rules

- Never set or change the type without the user saying so: it decides which licences the RC recommends.
- Never accept a scope the user has not agreed to.
- Never accept proposed tags the user has not seen.
- Then offer the next step: ingest the profile's material (rc-ingest), propose tags from it, or run a scout.
