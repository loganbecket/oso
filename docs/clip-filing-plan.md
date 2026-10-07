# Filing clips without typing: plan

Temporary planning document. Delete it when this ships. A small feature release: the next 0.x.0.

## Goal

He clips pages with the Obsidian clipper and moves on. Oso works out which course each clip belongs to and files it into that course's Readings folder, where it is searched like everything else. Today he has to type the course, exactly, in the clipper's course box; otherwise the clip sits unsorted in Clippings.

## How Oso decides

- On every check, each clip in Clippings with no course is compared with each active course, using the small search model Oso already runs on the laptop. No Claude usage.
- A course is described by what Oso already has for it: its name, its syllabus, its topic list, and its notes, readings, and book text. A new course with few notes still has its syllabus and topics.
- A clip is filed when one course is a clear match: close enough, and clearly closer than the next course. Anything else stays in Clippings and is asked about (below).
- Finished courses are never chosen.

## Pages from online textbooks

- The clipper keeps its "book" and "page" boxes. He pastes the book's title and types the page number; never the course.
- A clip with a book joins that book (searched as part of it, cited by page), in the course that already has a book by that name; a partial title is enough ("Halliday" finds "Fundamentals of Physics, Halliday").
- The first page of a book Oso hasn't seen gets its course in this order: (1) the course whose syllabus names the book as a required or recommended text (every course has a syllabus first, so this nearly always settles it, related courses included); (2) failing that, the page's content matched against the courses' material, the same way as any clip; (3) failing that, the briefing asks. Every later page of that book follows it.
- If a book lands in the wrong course, he tells Claude ("Halliday is for Physics 2, not Physics 1") and the whole book moves, every page clipped so far and every page after.

## What stays put

- **Syllabi.** Before filing a clip, Oso checks whether it looks like a syllabus ("syllabus", "grading", "office hours", "course schedule" in its title or headings). If it does, it stays in Clippings for `/create-course` to find, so a syllabus can't be filed into a similar existing course (Calculus III's into Calculus II).
- **Backup search during course setup.** Only when `/create-course` runs and finds no syllabus in Clippings, it also looks through clips Oso filed recently; if the syllabus is there, it uses it and moves it into the new course. At no other time does this search run.
- Anything that matches no course at all.

## Fixing a wrong guess

He tells Claude ("that article was for history, not physics"), and Claude moves it with a new Oso tool. Filing never edits the clip's text.

## Done when

- Tests: clips filed to the right course from sample course material; an ambiguous clip and an unrelated clip left in Clippings; a syllabus left in Clippings; course setup finding a syllabus that was filed anyway; finished courses skipped; moving a clip on request; a book's course found from the syllabus that names it; pages of the same book following the first; moving a whole book.
- A real run on his laptop with a handful of clips across his courses.

## Decisions (Logan's, 2026-10-07)

1. **Clips Oso can't place:** the morning briefing lists them and he tells Claude which course. No Claude usage until he answers.
2. **What was filed:** one briefing line, e.g. "Filed 6 clips: 4 Physics, 2 History".
3. **The course box:** removed from the clipper template. Oso always decides; he corrects through Claude. He re-imports the template once after the update (the old one keeps working meanwhile; a course typed in it is still honored).
4. **How sure:** cautious. Only clear matches are filed; the rest are asked about.
