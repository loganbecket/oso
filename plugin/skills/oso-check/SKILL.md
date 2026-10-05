---
name: oso-check
description: Review the student's own attempt at a problem, find where it goes wrong, and teach the method before giving an answer. Use when the student shares their work, a photo of it, or asks "is this right".
---

# Check my work

1. Identify the course and state its `ai_policy` in one line. If the policy forbids AI help on this kind of work, say so and stop.
2. Read the attempt fully (text, or the image they attach). Find the first point where it goes wrong, if any.
3. `search_notes` for the method in the course materials and open the source, so the correction uses the course's own notation and approach.
4. Respond in this order:
   - What is right so far, in one line.
   - The first mistake, named precisely ("the chain rule was applied to the outer function only"), with the relevant rule quoted from the notes and cited as `[[path]]`.
   - A nudge: the next step they should take, as a question or a hint, not the answer.
   - Only if they ask again, or say they are done trying: the full worked solution.
5. If the attempt is correct, say so, and point out one thing that would make it clearer or faster.
6. Add a line to `Courses/<folder>/Notes/Practice log.md`: `- YYYY-MM-DD | <topic> | <right or wrong> | check`.

Never rewrite the attempt for them. Never produce a submittable answer to graded work.
