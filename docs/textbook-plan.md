# Textbooks and course materials as the authority: phased plan

Temporary planning document. Delete it when the last phase ships. This is a feature release: it ships as the next 0.x.0 after the ones already planned (Canvas v0.2.0, backup v0.3.0); the order can change.

## Goal

Oso already turns digital course files (PDF, EPUB, Office) into searchable text, and tutoring searches them alongside his notes. But three things are missing:

- Scanned books and handouts have no text, so Oso can't read them. The only route today is the handwriting transcriber, which spends one Claude call per page; a 500-page book would use up his Claude allowance.
- A whole textbook becomes one enormous note, with no chapters, sections, or page numbers, so answers can't point him to "Chapter 4.2, page 131."
- Tutoring treats his notes and the textbook as equals. His notes may be wrong or incomplete; the book should be the authority, with his notes as the way in.

This plan makes every book he owns a first-class, page-cited source in his vault, and has tutoring stand on the book first and check his notes against it.

## Principles

- **His books, his vault, his use.** Book text lives only inside his own vault (and so his own Drive and NAS backup). It is never sent anywhere else, shared, or published. Claude reads passages only to answer his own questions.
- **Every format he can open.** DRM-free PDFs and EPUBs, scans and phone photos of pages, pages printed to PDF from a reader app, and pages clipped from a web reader he is signed into.
- **No Claude spend on bulk reading.** Text is pulled from a book on the laptop: directly from digital files, and with the operating system's own built-in text recognition for scans (Windows and macOS both include one). Pages with handwriting, equations, tables, or drawings are read by Claude automatically in the background, within a daily limit (Phase 6).
- **The book is the authority.** When the book and his notes disagree, tutoring says so and goes with the book, citing both.
- **Done once, in the background.** A book is processed once when it appears and never again unless the file changes. Progress shows in `oso doctor` and the dashboard.

## Phase 1: Books as structured, page-cited sources

**Status:** built and tested; unreleased. Not yet tried on one of his real books.

- A `Books` folder in each course. Anything dropped there is treated as a book (anything elsewhere stays an ordinary course file).
- Each book becomes a folder of notes, one per chapter (and section, where the book has them), taken from the book's own table of contents or headings. Every passage keeps its printed page number.
- Front matter on each chapter note: course, book title, edition, chapter, page range, type `textbook`.
- A `Book.md` index for each book: title, author, edition, chapters with page ranges, and which chapters the syllabus assigns when (from the course setup's readings).
- Search returns book passages with chapter and page, so answers can cite "Serway, ch. 4.2, p. 131."
- Very large books are processed a chapter at a time, so a check is never held up.

**Done when**
- Tests cover splitting a sample PDF and EPUB into chapters with correct page numbers, and search returning page-cited passages.
- One of his real digital textbooks is in the vault with a correct chapter index.

## Phase 2: Scanned books and pages

**Status:** built and tested; unreleased. Not yet tried on one of his real books.

- Scans, photos, and image-only PDFs in `Books` are read with the operating system's built-in text recognition, page by page, on the laptop. No Claude usage, nothing to install on Windows or macOS.
- Each page's image is kept beside its text, so Claude can look at the real page when a question touches an equation, table, or figure that text recognition handles poorly.
- Pages that come out poorly (mostly equations, tables, or figures) are marked, and the index lists them until Claude has read them from their images in the background (Phase 6); that reading is saved so it is never paid for twice.
- A scan of a chapter at a time is fine: pages added later join the same book in page order.
- Handouts and worksheets that are scans get the same treatment outside `Books`, replacing today's "no text layer found" note.

**Done when**
- Tests cover recognizing a sample scanned page, keeping page order across separate scans, and flagging a page of equations.
- A real scanned chapter is searchable with page citations.

## Phase 3: Books he reads in a publisher's app or website

**Status:** built and tested; unreleased. Not yet tried on one of his real books.

- Instructions in the README and the setup command for each common case: printing chapters to PDF, exporting highlights and notes, clipping pages with the Obsidian Web Clipper into the book's folder, and screenshots of pages he has open, which go through the same text recognition as scans.
- Clipped and printed pages carry their page numbers where the reader shows them, and file into the right book and chapter on sync, like clippings do today.
- His highlights and margin notes from a reader app, where it can export them, come in as his own notes linked to the book's pages.

**Done when**
- One chapter from a publisher's reader is in the vault, filed under its book, with page numbers.

## Phase 4: Tutoring that stands on the book

**Status:** built and tested; unreleased. Not yet tried on one of his real books.

- Explain, study guide, quiz, summarize, check, and flashcards search the book first and his notes second, and cite both. "Not in your notes or your book:" marks general knowledge.
- When his notes contradict the book (a wrong formula, a sign error, a definition that is off), Claude says so plainly, shows both, and goes with the book.
- A **check my notes** command: for one lecture's notes or a whole chapter, Claude compares them against the matching book chapter and lists what is wrong, what is missing, and what the book covers that he skipped. It can save corrections beside his note, never inside it.
- Study guides and practice tests for an exam use the chapters the syllabus assigns to that exam, so practice covers the book's material and not only what he happened to write down.
- Readiness can flag an exam chapter that has no notes at all.

**Done when**
- Tests cover the search order and citations, and the check-my-notes output on a note with a planted error.
- On a real question, the answer cites a book page and, where they differ, his note.

## Phase 6: Hard pages read automatically

**Status:** built and tested; unreleased.

Nothing he imports should need him to say how to read it. Notes, scans, book pages, handouts, and photos mix printed text, handwriting, equations, tables, diagrams, and drawings; every page gets read properly without a command.

- **Sorting.** Printed text that the computer's own text recognition reads cleanly stays on the laptop at no cost. Pages with handwriting, equations, tables, diagrams, or drawings (the ones recognition reads poorly, and every handwritten page) go to Claude.
- **Claude reads them in the background**, through Claude Code on the laptop, one page per call: text word for word, equations in LaTeX, tables as tables, and each diagram or drawing described. The reading replaces the poor text in the book chapter, handout, or note, with the page image still linked.
- **Handwriting too.** Handwritten pages are transcribed automatically; `oso transcribe` remains for doing it right away.
- **No limit by default.** Oso reads everything waiting, most urgent first: his own handwritten notes, then pages from courses with the nearest exam, then the rest. A daily page limit in settings (off by default) is there if it uses too much of his plan. Each check stops starting new pages after a few minutes so it stays inside the time Windows allows a background check; the rest continue on the next check.
- **Visible.** `Today.md`, `oso doctor`, and `oso books` say how many pages are waiting.

**Done when**
- Tests cover sorting, the optional daily limit, the time limit per check, the priority order, and each kind of page being replaced in place.

## Phase 5: Wrap-up

**Status:** built and tested; unreleased. Not yet tried on one of his real books.

- README: where to put books, how scans and reader apps work, what Oso does with the text.
- Settings window: book processing progress, and re-processing a book (also `oso books` and `oso books --reprocess`).
- `oso fresh-start` keeps books by default (they are purchases, not Oso's records) and says so.
- Release. Delete this document.

## Decisions

Defaults below; easy to revisit.

1. **Text recognition for scans: the operating system's own.** It needs nothing installed and runs on the laptop. Weak on math; covered by Claude reading those pages from their image only when asked. The alternative, a dedicated recognition model downloaded by Oso, would read math better but adds a second model to the service, which the repo's rules currently allow only for search.
2. **Book folder per course, not one shared library.** A book used by two courses lives in the first and is linked from the second.
3. **Corrections to his notes are saved beside them, never inside them**, matching the rule that Oso never edits a note he wrote.
