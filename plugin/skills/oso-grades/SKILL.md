---
name: oso-grades
description: Where the student stands in a course and what they need on the rest. Use when asked about grades, current standing, what score is needed on a final, or whether a target grade is reachable.
---

# Grades and what-if

1. Identify the course (`list_courses`). Call `grade_summary` with its code.
2. If the student asks what they need, call `what_if` with the target percent. If they give a letter grade, use the cutoffs in `Course.md`; if none are recorded, ask.
3. Report in plain words:
   - the current percent and how much of the course it rests on ("you're at 87% with 40% of the grade in")
   - the needed average on the rest, and the note if the target is already secured or out of reach
   - each category's score in one line
4. State the assumption the calculator makes: within a category, ungraded items count the same as graded ones. If the weights do not sum to about 100, say that the syllabus weights may be incomplete and offer to fix them with `set_weight` or by re-running setup.
5. To record a grade the student tells you, call `record_grade` with the item id from `list_deadlines` (use `include_done`).

Never estimate a grade from nothing. If no graded items exist, say so.
