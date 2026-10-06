# Check my notes against the book

The student wants his notes checked against the textbook: one lecture's notes, a day's notes, or everything for a chapter.

1. Find his notes (`list_notes` on the course's `Notes` folder; pick by name or date) and read them with `read_note`.
2. Find the matching book chapter: `search_notes` with `source` "book" on the notes' main topics, or the chapter the student names (the chapter notes are in the course's `Books/<title>/` folder; `Book.md` lists them). Read the relevant pages. For a page read poorly, look at it with `book_page` and save your reading with `save_page_reading`.
3. Compare, and reply in three short lists, each item citing the book page and the place in his notes:
   - **Wrong**: formulas, signs, units, definitions, or claims in his notes that the book contradicts, with the book's version
   - **Missing**: things the book presents as central to this material that his notes leave out
   - **Not covered in lecture**: book sections in this chapter that his notes don't touch at all, so he knows to read them
   If his notes are right and complete, say so in one line.
4. Offer to save the corrections. Only if he says yes, write them to a new note beside his, named `<his note's name> - checked against book.md`, with front matter `type: note-check`, `course`, `checks: [[his note]]`, `book`. Never edit his note itself.

The book is the authority, but say when a difference might be his instructor's own convention (different notation, a different but equivalent form) rather than an error.
