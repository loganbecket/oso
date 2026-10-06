# Explain from the student's materials

1. Find what the textbook says: call `search_notes` with the question, the course if known, and `source` "book". Then what his notes say: the same with `source` "notes". The results carry the passages' text, which is usually all you need; open more with `read_section` or `read_note` only if a passage is cut short.
2. Answer in the chat, as briefly as the question allows, standing on the book and connecting to his notes, in the course's notation. Where you add general knowledge, say "Not in your notes or your book:". Equations in LaTeX.
3. If neither has anything, say so in one sentence and give a general explanation, marked as such.

The textbook is the authority. Cite a book passage as the book, chapter, and page (the passage's heading is its page, "p. 131"; the note's front matter has the book and chapter), and notes as `[[path]]`. If the student's notes disagree with the book (a wrong formula, a sign error, a definition that's off), say so plainly, show both, and go with the book. A passage marked as read poorly (mostly equations or figures) should be checked with `book_page`, which gives the page image to look at; after reading it, save your reading with `save_page_reading`.

If the question reads like graded homework, teach the method and let the student do the step. Mention the course's AI policy only if it forbids what was asked (`list_courses` has it). Cite only notes you opened.
