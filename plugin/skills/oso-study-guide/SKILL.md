---
name: oso-study-guide
description: Build a study guide for an upcoming exam from the student's notes and materials, scoped to what the exam covers. Use when asked for a study guide, review sheet, or what to study for an exam.
---

# Study guide

1. Find the exam with `list_deadlines` (60 days) and what it covers from the course's `Course.md`. If the scope is not written down, ask for the lecture or chapter range.
2. Read the notes in scope (`list_notes` on the course folder, then `read_note` or `read_section`). Delegate the writing to the `oso-examiner` agent, passing the scope and these notes so it does not search again.
3. Show the guide in the chat:
   - the exam date and days left
   - one short section per topic, in the order taught: key ideas, formulas with symbols named, problem types and their method, with `[[path]]` citations
   - gaps: topics in scope with thin or no notes
   - a few practice problems if the student wants them, answers at the very end

Save it to `Courses/<folder>/Exams/<exam> study guide.md` only if the student asks. Never fill a gap with invented content; list it as a gap. The guide is a map, not a textbook.
