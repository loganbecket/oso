# Summarize

1. Find the material in as few steps as possible. If the student names a note, a day, or a lecture, call `list_notes` on that course's folder (for example `Courses/Physics/Notes`) and pick the match by name or date. Search more widely only if that finds nothing.
2. Read it with `read_note` (keep calling with `next_start` if it comes back in pieces).
3. Answer in the chat, at the length the student asked for. "Three sentences" means three sentences. With no length given, a short paragraph or five bullets at most.

Do not save a file unless the student asks for one. Do not look through other notes for connections unless asked. Do not add anything the material does not contain; if it is thin, say so in one line.
