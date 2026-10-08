# Notes and Handwriting

Everything you read and write for a class ends up in that course's folder in your vault, and Oso makes it searchable: web pages you clip, files your instructors post, shared Drive folders, and handwritten notes from your reMarkable tablet or paper scans.

## What it's for

Course material is scattered across Canvas, Google Drive, websites, a tablet, and paper. Claude can only help with what it can see. Oso gathers it into one place per course, on its own, and turns it into text Claude can search, so "explain this from my notes" actually means all your notes.

## How to use it

**Web pages.** Click the Obsidian Web Clipper, pick the **Oso** template, and save. There's no course to type. Within about half a minute Oso compares the page with each course's notes and materials and files it into the right course's `Readings` folder. When it can't tell, it leaves the page in `Clippings` and your morning briefing asks which course; tell Claude, or say it belongs to none. If it guesses wrong, say "that article was for history" and Claude moves it. A syllabus is never filed this way: it waits in `Clippings` for `/create-course`.

**Pages from an online textbook.** In the clipper, paste the book's title in the `book` box (part of the title is fine, as long as it's the same each time) and the page number in `page`. The page joins that book, in the course whose syllabus names it. See [Textbooks](textbooks.md).

**Course files.** With [Canvas connected](canvas.md), everything in each course's modules and Files section is copied into the course's `Canvas` folder, organized by module. Anything you drop into a course folder yourself works too. Word, PowerPoint, Excel, PDF, and LibreOffice files get a readable text copy next to them so Claude can search them. Google Docs, Sheets, and Slides stay in Google Drive; Oso leaves a short note with the link, and Claude reads them through its Google Drive connector.

**A shared Google Drive folder.** If an instructor shares a Drive folder of lecture files, Oso can copy it into the course folder on every check. See [Install guide: A shared Google Drive folder](../install.md#a-shared-google-drive-folder).

**Handwriting from the reMarkable.** Keep each class's notebooks in a tablet folder named exactly like the course folder in your vault (for example `Physics`). Plug the tablet in with its USB cable, and on the next check Oso copies any notebook you changed into the course's `Handwriting` folder. Oso then turns the pages into notes in the course's `Notes` folder on its own, in the background, with equations kept and every diagram described. Blank pages are skipped. Notebooks outside course folders, like a journal, are never touched.

**Paper notes.** Scan them with any phone scanning app and save the PDF into the course's `Handwriting` folder in your vault through Google Drive (for example `Vault/Courses/2026 Fall/Physics/Handwriting`). A photo works too. Scans saved anywhere outside a course folder are ignored.

**Search.** On every check Oso indexes your notes and course materials. Claude finds the right passage across your current classes in a fraction of a second, by meaning as well as exact words: a question about derivatives finds notes that only say "rate of change."

## Getting the most out of it

- Clip readings as you go. Filing is automatic, and clips become searchable right away.
- Leave the tablet plugged in at your desk for a few minutes after class; charging it there is enough.
- Label worked quiz answers with the question number in the top corner of the page (see [Studying](studying.md)).
- To have handwriting turned into notes right away instead of in the background, run `oso transcribe` or click **Transcribe now** in the Oso window.
- If a handwritten page came out wrong, fix the text in Obsidian. The original page image is linked at the bottom, and Oso never overwrites your edits.

## Setting it up

- Web Clipper: [Install guide: Accounts and apps](../install.md#accounts-and-apps)
- reMarkable: [Install guide: Your reMarkable tablet](../install.md#your-remarkable-tablet)
- Canvas files: [Install guide: Canvas sign-in](../install.md#canvas-sign-in)
- Shared Drive folder: [Install guide: A shared Google Drive folder](../install.md#a-shared-google-drive-folder)

## Good to know

- Filing clips uses a small search model on your computer, not Claude, so it costs nothing.
- Reading handwriting is the heaviest thing Oso asks of your Claude plan. In the Oso window's Settings tab you can set the picture size (1200 pixels tall by default; smaller is cheaper, larger reads tiny writing better), the model used for reading (Sonnet by default), and a daily page limit (none by default). Pages it couldn't read well are listed in your morning briefing.
- The first check after installing downloads the search model (about 65 MB). Indexing a big batch of new material can take a few minutes; later checks only index what changed.
- Finished courses are left out of everyday searches but can still be searched by name.
- No reMarkable account or subscription is needed; the tablet connects over its USB cable.
- Oso never edits a note you wrote.
