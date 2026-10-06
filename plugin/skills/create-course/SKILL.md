---
name: create-course
description: Set up a new course from its syllabus. Use when the student runs /create-course <name>, says they want to add or set up a course, or has clipped or dropped a syllabus into the vault.
argument-hint: <course name>
---

# Create a course

You are setting up one course in Oso from its syllabus. The course name, if given, is: $ARGUMENTS

The goal is a confirmed list of facts, not a guess. Nothing is written until the student confirms.

## Steps

1. **Find the syllabus.** Call `list_notes` with folder `Inbox`. The syllabus is usually the newest file there, clipped with the Obsidian Web Clipper (a Markdown note) or dropped in as a PDF. Pick the one whose title or name matches the course name; if more than one could be it, or none looks like a syllabus, ask the student which. If there is no syllabus, ask for it; do not invent dates. If no course name was given, take it from the syllabus.
2. **Read it** with `read_note` (follow `next_start` until the whole file is read) and extract:
   - the course code as Canvas labels it (for example `EGR-1301-001`; check `list_deadlines` for codes the Canvas feed already uses) and a short name
   - every dated item: assignments, quizzes, exams, projects, readings, with due dates and times
   - grade weights (what percentage each category or item is worth)
   - the instructor, office hours, and contact
   - the course's policy on AI tools, quoted as written
   - the late policy
3. **Show everything as one list** and ask the student to confirm or correct it. Dates that are relative ("week 6") need the student to confirm the actual date. Mention that the syllabus will be moved to `Courses/<name>/Syllabus.md`. Do not write anything until they confirm.
4. **After confirmation:**
   - call `add_course` with the code, the name, and the AI policy text; this creates the course folder and its subfolders
   - call `file_syllabus` with the code and the syllabus path from step 1; it moves the file into the course folder as `Syllabus` and tags it with the course
   - call `add_item` once per dated item, with `kind` of assignment, quiz, exam, reading, or event, the ISO due date, and the weight if known
   - write `Courses/<folder>/Course.md` in the vault using the template below
5. **Report** in two or three sentences: the course is set up, how many dates and grade weights were saved, and that the Canvas feed fills in anything the syllabus missed on the next check.

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
