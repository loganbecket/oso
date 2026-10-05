# Oso specification

## What it is

Oso is a study assistant for college students. It does two jobs. As a time manager it keeps one trusted picture of every deadline, exam, and grade weight across all courses and tells the student each morning what to do and why. As a study partner it reads the student's own notes and course materials to explain topics, build study guides, and generate practice tests, with a citation on every answer.

It is assembled, not built from scratch:

- **Obsidian** holds everything the student reads and writes, as Markdown files in a vault.
- **Claude** on a Pro subscription supplies the intelligence. The student uses Cowork on desktop and phone. Claude Code is used for installation and for jobs that must run locally against the vault.
- **A Python service** on the student's computer (Windows, macOS, or Linux) does the plumbing: pulls Canvas and the reMarkable tablet, converts files, keeps the deadline and grade database, notices changes, and writes a daily facts file into the vault.

There is no API account, no custom harness, no server, and nobody administering it. The student installs Oso once from this repo and owns it.

## Core promise

At the start of each semester, feed Oso the syllabus and course materials for every class. For the rest of the term it knows what is due, what matters, and what the student has already learned. Nothing in the daily path is bespoke: the student uses Obsidian and the Claude app, and Oso is what makes them know the courses.

## Principles

1. Buy the brain, build the plumbing.
2. Markdown for knowledge, SQLite for facts. The model never has to remember either.
3. One front door (Cowork), one notebook (Obsidian). A third app is a design failure.
4. Skills and MCP servers are built once and work from both Cowork and Claude Code.
5. Read-only toward the school. The only outside write is the student's own Google Calendar.
6. Cite or decline. When the notes hold nothing relevant, say so.
7. Zero-friction capture. Tablet pages, clipped pages, and course files flow in on their own.
8. Low noise. Only urgent changes interrupt; the rest waits for the morning briefing.
9. Fail visibly, in plain language, to the student.
10. Owned by the student. No backend, no administrator.
11. Respect each course's AI policy. Stored per course, shown at the start of every tutoring session.

## What Oso does

### Setting up a semester

The student drops each syllabus into the vault and runs the setup skill once per course. Oso reads the syllabus, proposes deadlines, exam dates, grade weights, office hours, and the professor's AI policy, and shows them for confirmation before anything goes live. Each course gets a folder in the vault and a course page holding those facts. Setup can be re-run for one course mid-term; the student's own corrections survive.

### Capturing what the student reads and writes

Pages written on the reMarkable are pulled over USB whenever the tablet is plugged in, transcribed to text with equations preserved, and filed under the right course with the original page image linked. Articles and papers read in the browser go into the vault with one click through the Obsidian Web Clipper, tagged with course and source. Files posted in Canvas or Google Drive are mirrored into the course folder; Word, PowerPoint, Excel, and PDF files get a readable text version beside the original. Every note carries course, topic, and type in its front matter. Search is full-text to begin with; embeddings only if that proves insufficient.

### Knowing what is due

One list of every assignment, quiz, exam, and reading across all courses, with due date, weight, status, and source. Deadlines come from the Canvas calendar feed, which every student account has, and from the Canvas API where the school allows student tokens, which adds grades and files. Duplicates across sources are merged; hand edits survive syncs. From this list Oso ranks what matters, flags a crunch week two weeks out, tracks grades, and answers what is needed on the final to hit a target.

### Hearing about changes

Every 15 minutes (adjustable) the service checks each source against its last snapshot. A moved due date, a rescheduled exam, or a new graded item due within the week is urgent: it becomes an event with a reminder on the student's Google Calendar. Everything else waits for the morning. Quiet hours and per-course muting are available. A broken connector or an expired login shows up in the briefing as a sentence.

### The morning briefing

The service writes the day's facts into `Today.md` in the vault on every check: due today, due this week, overnight changes, exam countdowns, connector problems, pages that transcribed badly. A scheduled Cowork task each morning reads it through Google Drive and delivers the briefing in the Claude app on the phone, which works while the laptop sleeps. A local Claude Code run is the fallback. A Sunday review covers the week behind and the week ahead.

### Studying

In Cowork the student asks anything about their courses and gets an answer built from their own notes, with a citation to the note or page. Available on request: a study guide scoped to an exam, a practice test with the key held back until attempted, a lecture or chapter summary, flashcards into Obsidian, a review of their own attempt at a problem that teaches the method before showing the answer, and a study plan placed on the calendar working back from exam dates. Oso tracks which topics go wrong and leans practice toward them. Every session opens with the course's AI policy.

### Where the student uses it

Cowork on laptop or phone is the one place to ask Oso anything. Obsidian is the one place to write and read notes. Claude in Chrome answers questions about the page being read. Google Calendar carries alerts and study blocks. Voice is the Claude mobile app's voice mode. The student never sees the service, the database, or a terminal.

## Architecture

The vault is the center. The service fills it and keeps the SQLite facts file beside it. Cowork and Claude Code read both through one Claude plugin of skills and MCP servers. Google Drive for Desktop carries the vault to the phone and to Anthropic's cloud for the scheduled briefing.

| Piece | Choice |
| --- | --- |
| Front door | Claude Cowork on desktop, web, and mobile |
| Installation and local runs | Claude Code |
| Notes | Obsidian with the Web Clipper; vault in a folder synced to Google Drive (Drive for Desktop on Windows and macOS, rclone on Linux) |
| Skills and tools | One Claude plugin installed in Cowork and Claude Code |
| Service | Python 3.12; every 15 minutes on Windows Task Scheduler, a macOS launch agent, or a Linux systemd timer, with catch-up after sleep |
| Facts | One SQLite file |
| Search | SQLite FTS5 over the vault; sqlite-vec with local embeddings only if needed |
| Canvas | Calendar feed; REST API with a token where allowed |
| reMarkable | Built-in USB web interface: notebooks downloaded as PDFs when plugged in, pages rendered to PNG, transcribed by a Claude Code run on the laptop |
| Office and PDF | python-docx, openpyxl, python-pptx, pypdf to Markdown |
| Google | Built-in Drive, Gmail, and Calendar connectors; one dedicated calendar is the only write |
| Browser | Claude in Chrome |
| Secrets | The operating system's credential store (Windows Credential Manager, macOS Keychain, Linux Secret Service) |

## Privacy and integrity

Course content reaches Anthropic only when the student asks Cowork or Claude Code something, under the consumer terms of their subscription. The account's data-use setting is reviewed and set deliberately at install. The cloud briefing reads only `Today.md` and what the briefing needs. Logs hold no credentials and no note content. Export is copying a folder; wipe is deleting it. The tutor teaches and checks work; it never produces submittable answers, and each course's AI policy is shown at every session.

## Open questions

- Does the school allow student-generated Canvas access tokens?
- Which publisher or lab sites does each course use, and do they offer feeds or email alerts?
- reMarkable Paper Pro or reMarkable 2? Both have the USB web interface.
- Pro or Max? Decide after Phase 1 usage is measured.
- Chrome or another browser?
- Each course's AI policy.
- Study blocks written to the calendar automatically, or only suggested?
- Public or private repository?

## Success metrics

- Zero missed deadlines attributable to information Oso had.
- The briefing is on the phone by the set time on at least 95 percent of mornings.
- Urgent alerts land within one polling interval of the change at the source, and fewer than one false-urgent alert per week after tuning.
- Handwritten pages are indexed within 12 hours of being written, with fewer than one in ten flagged for review.
- Tutor answers cite a correct source passage in the large majority of spot checks.
- Pro usage limits are hit no more than once a month; if more, upgrade.
- No connector is silently stale for more than 24 hours.
- The student opens the briefing most days and asks Oso something most study sessions.
- Nobody but the student has touched it since installation.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Pro usage limits bind during exam weeks | Measure in Phase 1; move transcription to a local vision model; upgrade to Max |
| The cloud briefing task cannot reach the laptop | The service writes the day's facts into the vault, Drive syncs it, the task reads it there; a local Claude Code run is the fallback |
| Vault sync conflicts between Drive and Obsidian | The service writes only to Inbox and generated files |
| Four apps feel like tool sprawl | Cowork is the only place to ask and Obsidian the only place to write; the service, connectors, and plugin are invisible |
| Handwriting transcription misreads equations | Page image linked from every transcript, confidence shown, corrections made in place; test on real handwriting in Phase 2 |
| School disables Canvas tokens | The calendar feed is the primary path and cannot be blocked; the token only adds grades and files |
| Subscription terms change | Oso never calls a model itself; all model use is inside Claude products. Re-check the terms each semester |
| The tutor is confidently wrong on technical material | Citations required, decline on empty retrieval, and a small per-course set of solved problems to spot-check against |
| Academic-integrity concerns | Per-course AI policy captured and displayed; tutor teaches and checks rather than answers; nothing is ever submitted |
| It breaks mid-semester with nobody maintaining it | Problems appear in the briefing in plain language; a self-service health check repairs the common failures; the fix for anything else is in the repo |
| Scope creep | Ship Phase 1 and use it for two weeks before starting Phase 2 |
