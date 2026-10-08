# Textbooks

Put a textbook in a course's `Books` folder and Oso turns it into searchable notes, one per chapter, with every page marked by its printed page number. Claude then answers from the book and cites it: "Serway, ch. 4.2, p. 131."

## What it's for

Your notes are only as good as what you caught in lecture. The textbook is the authority. With the book in Oso, explanations, study guides, and practice tests stand on it, cite exact pages, and catch mistakes in your notes. When your notes and the book disagree, Claude says so and goes with the book.

## How to use it

Drop the book in the course's `Books` folder (for example `Courses/2026 Fall/Physics/Books`). Then just study as usual: "Explain projectile motion" now answers from the book first.

- **A PDF or EPUB** (one without copy protection): drop the file in `Books`. Oso reads it on the next check. A big book takes a few checks; `oso books` shows how far along it is.
- **A scanned book or chapter, or photos of pages**: make a folder for the book with a `Scans` folder inside, `Books/<title>/Scans/`, and put the scans there, named so they sort in page order. Scans you add later join the end of the book.
- **A book in a publisher's app or website**: print chapters to PDF and drop them in `Books`. Or take screenshots of pages and put them in `Books/<title>/Scans/`. Or clip pages with the Web Clipper, typing the book's title in the `book` box and the page number in `page`; each clip joins that book (see [Notes and Handwriting](notes-and-handwriting.md)).
- **Highlights and notes** exported from a reader app go in `Books/<title>/Highlights/`. They're kept as your notes, not as the book.

Then:

- "Check my notes from Monday against the book." You get what's wrong, what's missing, and what the book covers that your notes skip. See [Studying](studying.md).
- "What does the book say about Newton's third law?" Claude quotes and cites the pages.

## Getting the most out of it

- Add the book as soon as the course is set up. Study guides and practice tests cover the chapters the syllabus assigns before each exam, not just what you wrote down.
- Prefer the digital file over scans when you can. It reads faster and more accurately.
- For scans, name the files so they sort in page order (`001.jpg`, `002.jpg`).
- Use "check my notes against the book" after each lecture, while the material is fresh.

## Good to know

- Printed text is read by your computer's own text recognition, so it costs none of your Claude plan.
- Pages with handwriting, equations, tables, diagrams, or drawings are read by Claude in the background, with equations kept and drawings described. You never have to ask. This uses some of your Claude plan; set a daily page limit in the Oso window's Settings tab if it uses too much (no limit by default).
- Book text stays in your vault on your computer and in your Google Drive.
- `oso books --reprocess "<title>"` reads a book again from the start.
- `oso fresh-start` keeps your books and what Oso has read of them.
- If a book lands in the wrong course, tell Claude and the whole book moves.
