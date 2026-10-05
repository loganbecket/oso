---
name: oso-setup
description: Set up a course for the semester from its syllabus. Use when the student says they want to add a course, set up a class, or has dropped a syllabus into the vault.
---

# Course setup

You are setting up one course in Oso from its syllabus. The goal is a confirmed list of facts, not a guess.

## Steps

1. Ask which course if it is not obvious, and find the syllabus. It is usually a PDF or Markdown file the student dropped into the vault (look in `Inbox/` and `Courses/`). If there is no syllabus, ask for it; do not invent dates.
2. Read the syllabus and extract:
   - the course code as Canvas labels it (for example `MATH-101-001`) and a short name
   - every dated item: assignments, quizzes, exams, projects, readings, with due dates and times
   - grade weights (what percentage each category or item is worth)
   - office hours and the instructor's contact
   - the course's policy on AI tools, quoted as written
   - the late policy
3. Show everything as one list and ask the student to confirm or correct it. Dates that are relative ("week 6") need the student to confirm the actual date. Do not write anything until they confirm.
4. After confirmation:
   - call `add_course` with the code, name, and the AI policy text
   - call `add_item` once per dated item, with `kind` of assignment, quiz, exam, reading, or event, the ISO due date, and the weight if known
   - write `Courses/<folder>/Course.md` in the vault using the template below
5. Tell the student the course is set up and that the Canvas feed will fill in anything the syllabus missed on the next sync.

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
