---
name: oso-transcribe
description: Transcribe handwritten tablet pages waiting in the vault into Markdown notes. Use when asked to transcribe notes, process handwriting, or when Today.md says pages are waiting. Runs in Claude Code on the laptop.
---

# Transcribe handwritten pages

Pages the student wrote on the tablet are waiting as images. Turn each notebook into one Markdown note.

## Steps

1. Call `pending_pages`. Group the results by `notebook`. If there are none, say so and stop.
2. Call `vault_path`, then for each notebook, read its page images in order (`<vault>/<path>`). Look at every page before writing.
3. Work out the course: the notebook name or the content usually says. If it is not clear, ask once, then remember for the session.
4. Write one note per notebook at `Courses/<course folder>/Notes/<YYYY-MM-DD> <notebook>.md` (date from the file's queued_at), with this front matter:

   ```
   ---
   type: notes
   course: <course code>
   topic: <two to five words>
   source: handwriting
   notebook: <notebook name>
   pages: <count>
   confidence: <0 to 1>
   ---
   ```

   Then the transcription: headings where the student drew them, lists as lists, equations in LaTeX (`$...$` inline, `$$...$$` display), diagrams described in one or two sentences in a blockquote beginning `> Figure:`. Keep the student's wording; fix nothing but obvious slips. Where a word or symbol is unreadable, write `[?]`. End each page's content with the image link: `![[<page path relative to vault>]]`.
5. Rate confidence per page honestly: 0.9 or above for clean handwriting fully read, 0.7 for a few `[?]`, below 0.5 if a page is mostly guesswork. Call `mark_transcribed` for every page with the note path and that page's confidence. The note's front matter carries the lowest page confidence.
6. Report what was written, with any low-confidence pages named so the student can check them.

## Rules

- Never invent content to fill a gap. `[?]` is correct; a plausible guess is not.
- Do not summarize. This is a transcription.
- Do not edit any note the student wrote by hand in Obsidian.
