# Oso build plan

Each phase ends at a gate the student can verify. The next phase starts only after the previous one has been in daily use for at least a week. Ship Phase 1 and use it for two weeks before starting Phase 2.

## Phase 0: accounts and vault

Mostly installing and signing in. Should take a weekend.

- [ ] Claude Pro subscription; review and set the data-use setting
- [ ] Claude desktop app with Cowork on Windows; Claude app on the phone
- [ ] Claude Code installed; this repo cloned
- [ ] Obsidian installed with the Web Clipper; clipper template that files by course and keeps source URL and date
- [ ] Google Drive for Desktop; vault folder inside it
- [ ] Google Drive, Gmail, and Calendar connectors signed in; one dedicated "Oso" calendar created
- [ ] `vault-template/` copied in: one folder per course (Lectures, Homework, Readings, Notes, Exams), `Inbox/`, `Course.md` template
- [x] Empty plugin skeleton installed in Cowork and Claude Code

**Gate:** the student clips an article and asks Cowork a question about it from their phone.

## Phase 1: the briefing

- [x] Service skeleton: config, logging without content, Windows scheduled task with wake timers, catch-up on wake
- [x] Windows Credential Manager wrapper
- [x] Canvas calendar feed connector, polled hourly
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

- [ ] reMarkable cloud connector: pull new or changed notebooks, render pages to PNG
- [ ] Transcription run in Claude Code: page image to Markdown with LaTeX, filed by course, image linked, confidence recorded
- [ ] Canvas Files and Modules mirrored into course folders (feed-based where possible, token if allowed)
- [ ] Office and PDF to Markdown conversion beside the original
- [ ] Front matter on every note: course, topic, type, source
- [ ] Full-text index over the vault exposed as an MCP search tool
- [ ] Skills: explain (with citations), study guide (scoped to an exam), quiz (key withheld until attempted), summarize
- [ ] Every tutoring skill opens with the course's AI policy and declines on empty retrieval

**Gate:** a page written on the tablet is searchable with a cited answer by the next morning, and a practice test comes back for a real exam.

## Phase 3: alerts and grades

- [ ] Hourly diff against the last snapshot; rule-based urgent versus routine classification
- [ ] Urgent changes written as events with reminders to the Oso calendar, and noted in `Inbox/`
- [ ] Quiet hours and per-course mute
- [ ] Grade tracking from Canvas or manual entry
- [ ] What-if calculator skill
- [ ] Plan skill: study blocks on the calendar working back from exam dates

**Gate:** a moved due date appears on the calendar at the next poll, and the what-if number is right.

## Phase 4: polish and handoff

- [ ] Canvas API token connector where the school allows it: announcements, grades, files
- [ ] Google Drive course folder mirroring and conversion
- [ ] Check skill: review the student's attempt, teach the method before the answer
- [ ] Weak-area tracking in the vault; practice weighted toward it
- [ ] Flashcards into Obsidian
- [ ] Sunday review
- [ ] `Dashboard.md`: deadlines, connector health, recent changes
- [ ] Nudge for items due within 24 hours not marked started
- [ ] Self-service health check and repair skill
- [ ] Browser automation for publisher sites with no feed
- [ ] Installer good enough that another student can set Oso up from this repo
