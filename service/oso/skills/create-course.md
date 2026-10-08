# Create a course

You are setting up one course in Oso from its syllabus. The course name, if given, is in the student's request.

The goal is a confirmed list of facts, not a guess. Nothing is written until the student confirms.

## Steps

1. **Find the syllabus.** Call `list_notes` with folder `Clippings`. The syllabus is usually the newest file there, clipped with the Obsidian Web Clipper (a Markdown note) or dropped in as a PDF. Pick the one whose title or name matches the course name; if more than one could be it, or none looks like a syllabus, ask the student which. If none of the clips there is the syllabus, call `recently_filed_clips`: Oso files clips into courses on its own, and may have filed the syllabus as a reading; if one of those is the syllabus, use it (`read_note` on its `dest`), and `file_syllabus` moves it into the new course later. If there is still no syllabus, ask for it; do not invent dates. If no course name was given, take it from the syllabus.
2. **Read it** with `read_note` (follow `next_start` until the whole file is read) and extract:
   - the course code as Canvas labels it (for example `EGR-1301-001`; check `list_deadlines` for codes the Canvas feed already uses) and a short name
   - every dated item: assignments, quizzes, exams, projects, readings, with due dates and times
   - grade weights (what percentage each category or item is worth)
   - the instructor, office hours, and contact
   - the course's policy on AI tools, quoted as written
   - the late policy
   - the term, like `2026 Fall` or `2027 Spring`, from the syllabus or its dates (January to May is Spring, June and July Summer, August to December Fall)
   - prerequisites, if listed
   - any website the instructor posts materials on (outside Canvas), if the syllabus names one
   - **class times (required)**: every meeting (lecture, lab, discussion) with its days, start and end times, and room; the first and last day of classes; and days with no class (holidays, breaks). Canvas doesn't have these, so they come from the syllabus or from him. If the syllabus doesn't give them, ask for them (his registration schedule has them); setup isn't finished without them
   - the topics, in the order taught, with the week each is covered and which exams cover it when the syllabus says (a schedule table usually lists them week by week). Use the course's own names for topics, at the grain of a lecture or chapter section ("Projectile motion", not "Physics")
3. **Check for related courses.** Call `list_courses`. If an earlier course is a prerequisite or clearly the one this builds on (Calculus II before Calculus III), propose relating them, so searches in the new course include the earlier course's notes.
4. **Show everything as one list** and ask the student to confirm or correct it, including the term and any related courses. Dates that are relative ("week 6") need the student to confirm the actual date. Show the topic list compactly (one line per week). If the syllabus names an instructor website, offer to have Oso follow it for new materials, and ask whether there are others. Mention that the course folder will be `Courses/<term>/<name>` with the syllabus inside it. Do not write anything until they confirm.
5. **After confirmation:**
   - call `add_course` with the code, the name, the term, the related course codes, and the AI policy text; this creates the course folder and its subfolders
   - call `course_topics` with the code and the confirmed topics (name, week, exams)
   - call `class_times` with the code, the meetings, the first and last day of classes, and the days with no class; the classes go on his calendar and stay current as instructors cancel or move them
   - for each instructor website the student wants followed, call `update_course` with `add_site`
   - call `file_syllabus` with the code and the syllabus path from step 1; it moves the file into the course folder as `Syllabus` and tags it with the course
   - call `add_item` once per dated item, with `kind` of assignment, quiz, exam, reading, or event, the ISO due date, and the weight if known
   - write `Courses/<folder>/Course.md` in the vault using the template below
6. **Report** in two or three sentences: the course is set up and its classes are on his calendar, how many dates and grade weights were saved, and that the Canvas feed fills in anything the syllabus missed on the next check.

## Course.md template

```markdown
---
type: course
code: MATH-101-001
name: Calculus I
instructor:
office_hours:
ai_policy: |
  (quoted from the syllabus)
late_policy: |
  (quoted from the syllabus)
---

# Calculus I

Syllabus: [[Courses/<folder>/Syllabus]]

## Class times
| Meeting | Days | Time | Room |
| --- | --- | --- | --- |

## Grading
| Component | Weight |
| --- | --- |

## Exams
| Exam | Date | Covers |
| --- | --- | --- |

## Readings
```dataview
TABLE clipped AS "Clipped", source AS "Source"
FROM "Courses/<folder>/Readings"
SORT clipped DESC
```

## Notes
```dataview
LIST
FROM "Courses/<folder>/Notes"
SORT file.mtime DESC
```
```

(The two `dataview` blocks render as live lists if the student has the Dataview plugin; otherwise they show as code and do no harm.)

## Rules

- Never submit, post, or change anything in Canvas or any school system.
- Quote the AI policy verbatim. If the syllabus says nothing about AI, record "not stated" and tell the student to ask the instructor.
- If setup is being re-run for a course that exists, `add_item` updates existing syllabus items in place and the student's own edits are kept.
