# Oso

A study assistant for college students that keeps track of what is due and helps them learn from their own notes.

Oso is assembled from three things: an Obsidian vault that holds everything the student reads and writes, Claude on a Pro subscription (Cowork for everyday use, Claude Code for installation) for intelligence, and a small Python service on the student's Windows laptop that pulls Canvas and the reMarkable tablet, keeps the deadline and grade database, and notices when something changes. There is no server, no API account, and nobody administering it. A student installs it once and owns it.

What it does:

- One trusted list of every deadline, exam, and grade weight across all courses
- A morning briefing on the phone saying what to do today and why
- Alerts on the calendar when a due date moves or something new is posted
- A tutor that answers from the student's own notes, with a citation on every answer
- Study guides, practice tests, and flashcards scoped to each exam
- Handwritten pages, clipped web pages, and course files captured without exporting anything

See [docs/spec.md](docs/spec.md) for the full description and [docs/plan.md](docs/plan.md) for the build plan.

## License

MIT. See [LICENSE](LICENSE).
