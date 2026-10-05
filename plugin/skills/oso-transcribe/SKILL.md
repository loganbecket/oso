---
name: oso-transcribe
description: Transcribe handwritten tablet pages waiting in the vault into Markdown notes. Use when asked to transcribe notes, process handwriting, or when Today.md says pages are waiting. Runs in Claude Code on the laptop.
---

# Transcribe handwritten pages

Pages the student wrote on the tablet (or scanned from paper) are waiting as images. Turn each notebook into one Markdown note.

## Preferred: the command

Run `oso transcribe` in the terminal. It sends each page to Claude Code one at a time with the model from the student's settings, so page images never accumulate in one conversation, and it writes the notes and marks the pages itself. Report its summary line and stop. If the command is missing or fails, fall back to the steps below.

## Fallback: by hand, one page at a time

1. Call `pending_pages`. Group the results by `notebook`. If there are none, say so and stop.
2. Call `vault_path`. For each page, in order, delegate to the `oso-transcriber` agent with the image's full path (`<vault>/<path>`), its page number, notebook, and course, and collect its transcription and confidence. One page per delegation, so the images stay out of this conversation.
3. Each page carries its `course` (the tablet folder it came from). Use it; only pages dropped into `Inbox/Handwriting` by hand have no course, and for those ask once.
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
