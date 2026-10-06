# Quiz

1. Find the notes for the topic or exam the student named: `search_notes` for a topic, `list_notes` on the course folder for a named lecture or note, and for an exam its date from `list_deadlines`.
2. Write as many questions as the student wants; with no number, five. Model them on the homework and examples in the notes, and only ask what the materials can answer. For each, decide its topic (as the course names it), a finer theme, its type (multiple_choice, short_answer, worked_problem, conceptual), and its difficulty (easy, medium, hard).
3. Call `start_quiz` with the course code, the questions with those fields (plus the question text and its source note), the student's request in their words, and the source notes. If this is a retake of an earlier quiz, pass `retake_of` (find it with `recent_quizzes`). Then show the questions in the chat. Do not show answers.
4. When the student answers, mark each right, partly right, wrong, or skipped; for anything not fully right, show the method briefly with a `[[path]]` citation. Call `record_answers` with each result, the kind of mistake for anything not fully right (concept_gap, calculation_slip, misread_question, incomplete), and whether you gave a hint. If they try a question again, record it again; that counts as another attempt.
5. When grading is done, call `finish_quiz` and end with the score and the topic or two to review.

Recording is quiet: never mention the tools or ask the student about them. If a recording call fails, carry on with the quiz and say nothing.

For a full-length practice exam (the student asks for a practice test or exam), delegate the writing to the `oso-examiner` agent with the scope and the notes you gathered. Save a file only if the student asks. No answers before an attempt unless they say they are done trying.
