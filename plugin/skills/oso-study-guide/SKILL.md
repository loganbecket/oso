---
name: oso-study-guide
description: Build a study guide for an upcoming exam from the student's notes and materials, scoped to what the exam covers. Use when asked for a study guide, review sheet, or what to study for an exam.
---

# Study guide for an exam

## Scope first

1. Call `list_deadlines` with `days` large enough (60) and find the exam. If several, ask which.
2. Find what it covers: `read_note` on the course's `Course.md` (the Exams table), the syllabus, and any announcement mentioning the exam. If the scope is not stated anywhere, ask the student for the lecture or chapter range and say the guide is based on their answer.
3. Note the course's `ai_policy` and state it in one line at the top of the guide.

## Model

Delegate the writing to the `oso-examiner` agent, which runs on the model the student chose for exam preparation (Opus by default). Pass it the scope, the course's AI policy, and the source notes you gathered.

## Gather

- Search the course folder (`Courses/<folder>/`) with your file search for each topic in scope, opening the relevant sections with `read_section` (whole notes with `read_note` only when needed): lectures, the student's own notes, homework, and readings. Prefer the student's notes and the instructor's slides over textbook text.

## Write the guide

Save it as `Courses/<folder>/Exams/<exam name> study guide.md` with front matter (`type: study-guide`, `course`, `exam`, `generated`), then show it.

1. **Covers**: the scope and the exam date, countdown in days.
2. **Topics**, one section each, in the order taught: the key ideas in a few lines, the formulas with what each symbol means, the standard problem types and the method for each, common mistakes the notes or homework show. Every section cites its sources as `[[path]]`.
3. **Practice**: three to five problems per topic drawn from or modeled on the homework, with answers at the very end under a heading the student can avoid.
4. **Gaps**: topics in scope with thin or no notes, so the student knows what to review from the textbook or ask about in office hours.
5. **Plan**: how to split the remaining days across the topics, weighted toward the gaps and the heavier topics.

## Rules

- Cite only notes you opened. Never fill a gap with invented course content; list it under Gaps instead.
- Short sections. The guide is a map, not a textbook.
