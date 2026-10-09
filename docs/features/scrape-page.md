# Saving Textbook Pages from Chrome

Run `/scrape-page` with a course name while an online textbook page is open in Chrome, and Claude reads the page and saves all of it as part of that course's book. Diagrams, graphs, and tables are written out in words, so nothing on the page is lost.

## What it's for

Many textbooks only live on a publisher's website, where they can't be downloaded or printed. Those pages are full of figures that a copy-and-paste or a web clipping drops. This command has Claude read the page the way you see it, figures included, so explanations, study guides, practice tests, and note checks can draw on it and cite it by page, the same as a textbook you dropped in the `Books` folder.

## How to use it

1. Open the textbook page in Chrome.
2. In the Claude app, type `/scrape-page` and the course, for example `/scrape-page Physics`.

Claude finds the book's title and page number on the page, transcribes everything in order, and tells you in one line what it saved. If it can't tell which book the page is from, it asks once.

What you get:

- The full text, word for word, not a summary.
- Equations kept as equations, even when the site shows them as pictures.
- Tables with every cell.
- Every figure described: its caption, every label, axis, and value, and what it shows. Detailed enough that Claude can answer a question about the figure later without seeing it.

## Getting the most out of it

- Save each assigned page as you read it. Study guides and practice tests then cover the reading, not just your lecture notes.
- Use the same book for the whole course: once one page is saved, later pages join the same book automatically.
- Running it again on the same page replaces the earlier copy, so redo a page if something came out wrong.
- One page at a time. For a whole chapter, run it on each page.
- If a page can't be copied word for word, Claude saves a detailed summary instead (every heading, equation, table, and figure) and says so, rather than leaving a half-saved page.

## Good to know

- It needs the Claude in Chrome extension (see [Install guide: Claude in Chrome](../install.md#claude-in-chrome)).
- Claude only reads the page. It never clicks answers, submits anything, or marks your progress on the publisher's site.
- Pictures themselves aren't saved, only their descriptions. Publisher sites usually block saving them, and the descriptions are what Claude uses.
- Reading a page with figures uses some of your Claude plan.
- When the site has no page numbers, the page is saved under its section number and title instead.
