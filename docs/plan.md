# Oso build plan

Each phase ends at a gate the student can verify. The next phase starts only after the previous one has been in daily use for at least a week. Ship Phase 1 and use it for two weeks before starting Phase 2.

## Phase 0: accounts and vault

Mostly installing and signing in. Should take a weekend.

- [ ] Claude Pro subscription; review and set the data-use setting
- [ ] Claude desktop app with Cowork on Windows; Claude app on the phone
- [ ] Claude Code installed; this repo cloned
- [x] Obsidian with the Web Clipper, an Oso clipper template that keeps source and date, filing into the course on sync, and the Spaced Repetition plugin for flashcards
- [ ] Google Drive for Desktop; vault folder inside it
- [ ] Google Drive, Gmail, and Calendar connectors signed in; one dedicated "Oso" calendar created
- [ ] `vault-template/` copied in: one folder per course (Lectures, Homework, Readings, Notes, Exams), `Inbox/`, `Course.md` template
- [x] Empty plugin skeleton installed in Cowork and Claude Code

**Gate:** the student clips an article and asks Cowork a question about it from their phone.

## Phase 1: the briefing

- [x] Service skeleton: config, logging without content, Windows scheduled task with wake timers, catch-up on wake
- [x] Windows Credential Manager wrapper
- [x] Canvas calendar feed connector, polled on every check
- [x] SQLite schema: courses, items (assignment, quiz, exam, reading), due dates, weights, status, source
- [x] Duplicate merging across sources; hand edits survive sync
- [x] Per-connector health: last sync, last error, re-auth needed
- [x] `Today.md` writer: due today, due this week, changes, exam countdowns, connector problems
- [x] MCP server over SQLite: list deadlines, get course, update status, record grade
- [x] Setup skill: read a syllabus from the vault, propose dates, weights, office hours, AI policy; confirm; write `Course.md` and the database
- [x] Briefing skill, run as a scheduled Cowork task each morning reading `Today.md` via Drive
- [x] Fallback: the same briefing from a local Claude Code run

**Gate:** the morning briefing in the Claude app on the phone lists every deadline from Canvas and the calendar.

## Phase 2: notes and tutor

- [x] Tablet pages: a tablet folder named after a course folder is pulled over USB into `Courses/<folder>/Handwriting`; pages are rendered to PNG and queued with their course
- [x] Transcription: `oso transcribe` sends one page per Claude Code call with the configured model; blank pages skipped; image size configurable; notes filed by course with image links and confidence
- [x] Model defaults: Sonnet for handwriting, Opus for study guides and practice tests, set in the settings window and applied through plugin agents
- [x] Canvas Files and Modules mirrored into course folders (feed-based where possible, token if allowed)
- [x] Office, LibreOffice, and PDF to Markdown beside the original (MarkItDown plus LibreOffice headless); pointer notes for Google Docs
- [x] Front matter on every note: course, topic, type, source
- [x] Search through Claude's own file search over the Markdown copies (the separate index was removed)
- [x] Skills: explain (with citations), study guide (scoped to an exam), quiz (key withheld until attempted), summarize
- [x] Every tutoring skill opens with the course's AI policy and declines on empty retrieval

**Gate:** a page written on the tablet is searchable with a cited answer by the next morning, and a practice test comes back for a real exam.

## Phase 3: alerts and grades

- [x] Diff against the last snapshot on every check (15 minutes by default, set in the settings window); rule-based urgent versus routine classification
- [x] Urgent changes written by the service straight to its own Oso Google calendar (Calendar API, app-created calendars only), and noted in `Inbox/`
- [x] Quiet hours and per-course mute
- [x] Grade tracking from Canvas or manual entry
- [x] What-if calculator skill
- [x] Plan skill: study blocks on the calendar working back from exam dates

**Gate:** a moved due date appears on the calendar at the next poll, and the what-if number is right.

## Phase 4: polish and handoff

- [x] Canvas API token connector where the school allows it: announcements, grades, files
- [x] Pull notebooks straight off the reMarkable over USB (its built-in USB web interface); no cloud account needed
- [x] Google Drive course folder mirroring and conversion
- [x] Check skill: review the student's attempt, teach the method before the answer
- [x] Weak-area tracking in the vault; practice weighted toward it
- [x] Flashcards into Obsidian
- [x] Sunday review
- [x] `Dashboard.md`: deadlines, connector health, recent changes
- [x] Nudge for items due within 24 hours not marked started
- [x] Self-service health check and repair skill
- [x] `oso update`: pull and reinstall in one step; daily check that shows in the briefing and the doctor
- [x] Settings window (`oso settings`): check interval, urgency window, quiet hours, mutes, tablet folder, Canvas feed and token
- [ ] Browser automation for publisher sites with no feed
- [x] Installer good enough that another student can set Oso up from this repo
