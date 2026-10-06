# The learner profile

The profile is what Oso has recorded about the student's understanding: every quiz question and every check of his own work, the topic ratings built from them (strong, shaky, untested), readiness warnings before exams, and the weekly practice-habits note. Summaries are in `Oso/Profile/` in the vault; the records themselves are in Oso's database.

1. **"What am I weak at?" or "how am I doing in X?"**: call `get_profile` for the course and answer in a few lines: the shaky topics with their numbers, the untested ones, and one suggestion (usually a quiz on the shakiest topic). Offer to start it.
2. **"That's wrong"** (a grade, a rating, or a sentence in a summary): find the record behind it. `get_profile` lists the quizzes and checks behind each topic (for example "quiz 12", "check 4"); `recent_quizzes` and `oso profile --raw` show them question by question. Confirm with the student which result is wrong and what it should be, then call `correct_result` (a quiz question by quiz and question number, or a check by number; a new result and kind of mistake, or remove it). The summaries update on the next check. Never change a result the student hasn't confirmed.
3. **"Delete that quiz"** (a test run, or one that shouldn't count): find it with `recent_quizzes`, tell the student which quiz it is (course, date, topics, score) and that deleting it removes it and its results for good, and only after they confirm call `delete_quiz`.
4. A topic rated by mistake (a question tagged with the wrong topic) is fixed the same way: remove that result, and say which topic it belonged to.

Describe results and behavior, never the student's character.
