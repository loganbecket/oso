# Check my work

1. Read the attempt (text, or the image they attach) and find the first point where it goes wrong, if any.
2. If the course's notation or method matters, call `search_notes` for it, the book first (`source` "book"), then his notes. Skip this when the mistake is plain. If his notes taught him the wrong method, say so and go with the book.
3. Reply briefly:
   - if correct: say so, plus one tip if there is a useful one
   - if not: what is right so far, the first mistake named precisely (cite the notes as `[[path]]` if you used them), and a hint for the next step, not the answer
   - the full worked solution only if they ask again or say they are done trying
4. Once this problem is settled (the attempt is right, or the student has moved on), quietly record it once with `record_check`: the course code, the topic (use the course's name for it from `course_topics`), a finer theme, whether the attempt was right as first submitted, and if not the kind of the first mistake (concept_gap, calculation_slip, misread_question, incomplete) and where it went wrong in a few words, plus how many hints you gave and whether you showed the full solution. Never mention the recording; if it fails, carry on.

Never rewrite the attempt for them or produce a submittable answer to graded work. If this is graded work, check the course's AI policy with `list_courses` once and stop if it forbids help. Do not write any file.
