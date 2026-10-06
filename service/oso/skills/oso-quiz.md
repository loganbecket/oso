# Quiz

Quizzes, tests, and practice exams are taken in Oso's quiz window on the student's computer, not in the chat.

1. Find the notes for the topic or exam the student named: `search_notes` for a topic, `list_notes` on the course folder for a named lecture or note, and for an exam its date from `list_deadlines`.
2. Write as many questions as the student wants; with no number, five. Model them on the homework and examples in the notes, and only ask what the materials can answer. For each, decide its topic (use the course's names from `course_topics`; a new name is fine when nothing fits), a finer theme, its type (multiple_choice, short_answer, worked_problem, conceptual), and its difficulty (easy, medium, hard). Multiple choice needs its choices and the correct letter. For a full-length practice exam, have the `oso-examiner` agent write the questions from the notes you gathered.
3. Call `start_quiz` with the course code, the questions (number, topic, theme, type, difficulty, question text, source note, and for multiple choice the choices and answer), the student's request in their words, the source notes, and `retake_of` if this retakes an earlier quiz (find it with `recent_quizzes`). Oso records it and opens the quiz window.
4. Tell the student in one or two lines: the quiz is open in the Oso window; for worked problems, write each answer on a page labeled with the question number in the top corner (paper or the reMarkable) and add the pages when the window asks; and to come back and say they're done. If the window could not open, give them the command `start_quiz` returned. Never show the questions or answers in the chat.
5. When the student says they're done, call `quiz_responses`. Multiple choice is already graded. Grade every other answer: typed responses directly, and written work by reading each page image in `written_work` and matching it to its question by the label in its corner (ask the student about any page you cannot match). Mark each right, partly right, wrong, or skipped.
6. Call `record_answers` for the questions you graded, with the kind of mistake for anything not fully right (concept_gap, calculation_slip, misread_question, incomplete). Then call `finish_quiz`.
7. Reply with the score, then for each question not fully right a brief note on the method with a `[[path]]` citation, then the topic or two to review.

If the student would rather answer in the chat (or the window is not available), call `start_quiz` with `window` false, show the questions in the chat without answers, and grade their reply the same way, recording each try at a question again as another attempt.

Recording is quiet: never mention the tools. If a recording call fails, carry on with the quiz and say nothing about it.
