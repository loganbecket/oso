# Filing clips without typing: plan

Temporary planning document. Delete it when this ships. A small feature release: the next 0.x.0.

## Goal

He clips pages with the Obsidian clipper and moves on. Oso works out which course each clip belongs to and files it into that course's Readings folder, where it is searched like everything else. Today he has to type the course, exactly, in the clipper's course box; otherwise the clip sits unsorted in Clippings.

## How Oso decides

- On every check, each clip in Clippings with no course is compared with each active course, using the small search model Oso already runs on the laptop. No Claude usage.
- A course is described by what Oso already has for it: its name, its syllabus, its topic list, and its notes, readings, and book text. A new course with few notes still has its syllabus and topics.
- A clip is filed when one course is a clear match: close enough, and clearly closer than the next course. Anything else stays in Clippings and is asked about (below).
- Finished courses are never chosen.

## What stays put

- A syllabus for a course that isn't set up yet stays in Clippings, where course setup looks for it, so it can't be filed into a similar existing course (Calculus III's syllabus into Calculus II).
- Anything that matches no course at all.

## Fixing a wrong guess

He tells Claude ("that article was for history, not physics"), and Claude moves it with a new Oso tool. Filing never edits the clip's text.

## Done when

- Tests: clips filed to the right course from sample course material; an ambiguous clip and an unrelated clip left in Clippings; a syllabus for an unset course left alone; finished courses skipped; partial typed names; moving a clip on request.
- A real run on his laptop with a handful of clips across his courses.

## Decisions (Logan's, 2026-10-07)

1. **Clips Oso can't place:** the morning briefing lists them and he tells Claude which course. No Claude usage until he answers.
2. **What was filed:** one briefing line, e.g. "Filed 6 clips: 4 Physics, 2 History".
3. **The course box:** removed from the clipper template. Oso always decides; he corrects through Claude. He re-imports the template once after the update (the old one keeps working meanwhile; a course typed in it is still honored).
4. **How sure:** cautious. Only clear matches are filed; the rest are asked about.
