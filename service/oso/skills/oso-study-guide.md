# Study guide

1. Find the exam with `list_deadlines` (60 days) and what it covers: the topics `course_topics` lists for that exam, and the course's `Course.md`. If the scope is not written down, ask for the lecture or chapter range.
2. Call `get_profile` for the course and note which topics in scope are shaky or untested; give those sections more depth and practice, and keep strong topics brief.
3. Gather the material in scope, the textbook first: the chapters the syllabus assigns before this exam (the book's `Book.md` lists the readings with dates), `search_notes` with `source` "book" once per topic, then `source` "notes" for his notes, and `list_notes` for named lectures. Delegate the writing to the `oso-examiner` agent, passing the scope and these notes so it does not search again.
4. Show the guide in the chat:
   - the exam date and days left
   - one short section per topic, in the order taught: key ideas, formulas with symbols named, problem types and their method, citing the book's chapter and page and his notes
   - where his notes disagree with the book, say so in that section and go with the book
   - gaps: assigned chapters or topics with thin or no notes of his
   - a few practice problems if the student wants them, answers at the very end

Save it to `Courses/<folder>/Exams/<exam> study guide.md` only if the student asks. Never fill a gap with invented content; list it as a gap. The guide is a map, not a textbook.
