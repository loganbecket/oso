---
name: oso-quiz
description: Generate a practice test from the student's materials and grade their attempt. Use when asked for a quiz, practice test, practice problems, or to be tested on a topic or exam.
---

# Practice test

## Build it

1. Settle the scope: an exam (via `list_deadlines` and `Course.md`) or a topic the student names. State the course's `ai_policy` in one line.
2. `search_notes` across the scope and open the sources. Questions must be answerable from the course materials; model them on the homework and examples the instructor used.
3. Write the test to `Courses/<folder>/Exams/Practice <topic or exam> <date>.md` with front matter (`type: practice-test`, `course`, `scope`, `generated`) and show it.
   - Default mix for a technical course: 4 short-answer or conceptual questions, 4 worked problems, 4 multiple choice. Adjust to what the student asks for.
   - Number every question. Note the source note for each as `[[path]]` in a comment line `<!-- source: ... -->` so the key can cite it.
   - **Do not include the answers.** Keep them to yourself until the student submits an attempt.

## Grade it

When the student sends answers:

- Mark each question right, partly right, or wrong, and for anything not fully right show the correct method step by step with the citation.
- Give a score and the two or three topics that need work.
- Append a `## Results` section to the practice test file: date, score, and the weak topics, and add one line per weak topic to `Courses/<folder>/Notes/Practice log.md` (create it if missing) in the form `- YYYY-MM-DD | <topic> | <right>/<total> | [[practice test path]]`. Later quizzes read this log and weight questions toward the weak topics.

## Rules

- No answers before an attempt, even if asked, unless the student says they are done trying.
- Never use a question you cannot source to the materials.
