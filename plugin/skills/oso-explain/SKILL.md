---
name: oso-explain
description: Answer a question about coursework from the student's own notes and materials, with citations. Use for any "explain", "what is", "how do I", "why does" question about a class topic.
---

# Explain from the student's materials

## Before answering

1. Identify the course. Call `list_courses` if needed and note its `ai_policy`. Begin the reply with one line: "Policy for <course>: <policy, shortened>" (or "no AI policy recorded; check with the instructor").
2. Call `search_notes` with the key terms, scoped to the course. Try two or three phrasings if the first returns little. Open the most relevant hits with `read_note`.

## Answer

- Build the explanation from what the notes and course materials say, in the order the course teaches it.
- Cite every claim drawn from the vault as `[[path]]` (the vault-relative path from `search_notes`), at the end of the sentence or paragraph it supports.
- Where general knowledge is needed to connect the student's notes, say so plainly: "Not in your notes, but:".
- Equations in LaTeX. Worked steps shown one at a time.
- End with one check-your-understanding question.

## If the notes have nothing

Say so in one sentence, name what the student could add to the vault (a lecture, a chapter), and offer a general explanation only if they ask. Do not pretend the notes covered it.

## Never

- Produce a finished answer to something that reads like graded homework. Teach the method and let the student do the step.
- Cite a note you did not open.
