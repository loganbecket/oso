# Oso specification

## What it is

Oso is a study assistant for college students. It does two jobs. As a time manager it keeps one trusted picture of every deadline, exam, and grade weight across all courses and tells the student each morning what to do and why. As a study partner it reads the student's own notes and course materials to explain topics, build study guides, and generate practice tests, with a citation on every answer.

It is assembled, not built from scratch:

- **Obsidian** holds everything the student reads and writes, as Markdown files in a vault.
- **Claude** on a Pro subscription supplies the intelligence. The student uses Cowork on desktop and phone. Claude Code is used for installation and for jobs that must run locally against the vault.
- **A Python service** on the student's computer (Windows, macOS, or Linux) does the plumbing: pulls Canvas (and, for students who have one, a reMarkable tablet), converts files, keeps the deadline and grade database, notices changes, and writes a daily facts file into the vault.

There is no API account, no custom harness, no server, and nobody administering it. The student installs Oso once from this repo and owns it.

## Core promise

At the start of each semester, feed Oso the syllabus and course materials for every class. For the rest of the term it knows what is due, what matters, and what the student has already learned. Nothing in the daily path is bespoke: the student uses Obsidian and the Claude app, and Oso is what makes them know the courses.

## Principles

1. Buy the brain, build the plumbing.
2. Markdown for knowledge, SQLite for facts. The model never has to remember either.
3. One front door (Cowork), one notebook (Obsidian). A third app is a design failure.
4. Skills and MCP servers are built once and work from both Cowork and Claude Code.
5. Read-only toward the school.
6. Cite or decline. When the notes hold nothing relevant, say so.
7. Zero-friction capture. Scanned pages, clipped pages, and course files flow in on their own.
8. Low noise. Only urgent changes interrupt; the rest waits for the morning briefing.
9. Fail visibly, in plain language, to the student.
10. Owned by the student. No backend, no administrator.
11. Respect each course's AI policy. Stored per course, and raised whenever it forbids what the student asked.

## What Oso does

### Setting up a semester

The student drops each syllabus into the vault and runs the setup skill once per course. Oso reads the syllabus, proposes deadlines, exam dates, grade weights, office hours, and the professor's AI policy, and shows them for confirmation before anything goes live. Each course gets a folder in the vault and a course page holding those facts. Setup also requires the class times (every lecture, lab, and discussion, with room, the first and last day of classes, and days off), from the syllabus or asked for, since Canvas doesn't have them. Classes go on the Oso calendar three weeks ahead, rolling forward, and a class canceled or moved in an email, GroupMe, or a Canvas announcement changes that one meeting on the calendar. Setup can be re-run for one course mid-term; the student's own corrections survive.

### Capturing what the student reads and writes

Handwritten pages, scanned or photographed into a course's Handwriting folder (or pulled over USB from a reMarkable tablet, an optional extra for students who have one), are transcribed to text with equations preserved, and filed under the right course with the original page image linked. Articles and papers read in the browser go into the vault with one click through the Obsidian Web Clipper, tagged with course and source. A page of an online textbook open in Chrome is read by Claude in Chrome on request (`/scrape-page`) and saved into the course's copy of the book, word for word, with equations kept and each figure described in enough detail to answer questions about it. Files posted in Canvas or Google Drive are mirrored into the course folder; Word, PowerPoint, Excel, PDF, and LibreOffice files get a readable Markdown copy beside the original (Microsoft's MarkItDown, with LibreOffice converting its own formats when installed); Google Docs get a pointer note and are read through Claude's Drive connector. Every note carries course, topic, and type in its front matter. Claude finds material with its own file search over the course folder.

### Knowing what is due

One list of every assignment, quiz, exam, and reading across all courses, with due date, weight, status, and source. Deadlines come from the Canvas calendar feed, which every student account has, and from the Canvas API where the school allows student tokens, which adds grades and files. Duplicates across sources are merged; hand edits survive syncs. From this list Oso ranks what matters, flags a crunch week two weeks out, tracks grades, and answers what is needed on the final to hit a target.

### Hearing about changes

Every 15 minutes (adjustable) the service checks each source against its last snapshot. A moved due date, a rescheduled exam, or a new graded item due within the urgent window is urgent: the service puts it straight on the Oso Google calendar with reminders, without involving Claude. Everything else waits for the morning. Quiet hours and per-course muting are available. A broken connector or an expired login shows up in the briefing as a sentence.

### Knowing what the student knows

Every quiz (taken in Oso's quiz window, timed per question, with written work on paper, scanned or photographed) and every check of the student's own work is recorded: topic, result, kind of mistake, attempts, hints, and time. Each course's topic list comes from its syllabus, so a topic with no results is untested, never assumed known. From those results Oso rates each topic strong, shaky, or untested, aims quizzes and study guides at the weak ones, flags exams within a week that the student isn't ready for, and once a week describes practice habits (lead time before exams, follow-through on missed topics, trends, where practice goes) in behavior, never character. Summaries live in `Oso/Profile/`; the records live in SQLite. Oso does not read chats: test results are the evidence.

### The morning briefing

The service writes the day's facts into `Today.md` in the vault on every check: due today, due this week, overnight changes, exam countdowns, connector problems, pages that transcribed badly. A scheduled Cowork task each morning reads it through Google Drive and delivers the briefing in the Claude app on the phone, which works while the laptop sleeps. A local Claude Code run is the fallback. A Sunday review covers the week behind and the week ahead.

### Studying

In Cowork the student asks anything about their courses and gets an answer built from their own notes, with a citation to the note or page. Available on request: a study guide scoped to an exam, a practice test with the key held back until attempted, a lecture or chapter summary, flashcards into Obsidian, a review of their own attempt at a problem that teaches the method before showing the answer, and a study plan placed on the calendar working back from exam dates. Answers come back in the chat at the size asked for; Oso writes a file only when asked (flashcards excepted).

### Tasks

A checklist of things to get done that aren't coursework (laundry, an oil change, registering to vote), added by telling Claude, by voice or text, or on the phone in a Google Tasks list named Oso, and checked off in either place; the two are matched on every check. Things to do that Claude picks out of email, GroupMe, and Canvas join the list. Tasks have a day they should be done by, or none; the morning briefing shows what's open, overdue first, and suggests what fits today's free time. A reminder at a moment ("remind me to swing by the mail room on my way back to the dorm") is a pop-up event on the Oso calendar, timed from the class schedule. Google Tasks is the second outside write, after the Oso calendar, and only to the list Oso made.

### Rules

The student shapes Oso by saying what they want from now on, in any conversation. Claude asks "Want me to keep that as a rule?" and saves nothing without a yes. A rule is one note in `Oso/Rules/`, in the student's words, and `/oso-rules` lists, changes, pauses, or deletes them (plain requests work too). Fresh start erases them.

- **How Oso responds** ("give me the briefing as bullet highlights"): handed to the command it's about with that command's instructions, or, for everything, to every command and the vault's Claude instructions.
- **When something happens** ("when a new test date shows up, block three hours to study three days before"): saved with a short form the sync follows: what to watch (new deadlines and exams, grades, Canvas changes, school email and GroupMe), when to act, and what to do. On every check the sync compares what's new against each form; a calendar block it places itself in the earliest free time that avoids classes, the Oso calendar, and quiet hours (the nearest earlier day when the day is full), and anything needing judgment starts Claude in the background with only Oso's tools. Each rule acts once per thing; its block moves with the exam and is removed if the exam is canceled. The briefing says in a line what a rule did or why it couldn't. A note edited by hand is reread by Claude before the rule runs again.

There is no list of allowed rules: Claude turns down what Oso can't do, and Oso's own rules win (read-only toward school, honest reporting, the student's notes never edited); a rule that conflicts is turned down or narrowed, with the reason.

### Where the student uses it

Cowork on laptop or phone is the one place to ask Oso anything. Obsidian is the one place to write and read notes. Claude in Chrome answers questions about the page being read. Google Calendar carries alerts and study blocks. Voice is the Claude mobile app's voice mode. The student never sees the service, the database, or a terminal.

## Architecture

The vault is the center. The service fills it and keeps the SQLite facts file beside it. Cowork and Claude Code read both through one Claude plugin of skills and MCP servers. Google Drive for Desktop carries the vault to the phone and to Anthropic's cloud for the scheduled briefing.

| Piece                       | Choice                                                                                                                                                 |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Front door                  | Claude Cowork on desktop, web, and mobile                                                                                                              |
| Installation and local runs | Claude Code                                                                                                                                            |
| Notes                       | Obsidian with the Web Clipper; vault in a folder synced to Google Drive (Drive for Desktop on Windows and macOS, rclone on Linux)                      |
| Skills and tools            | One Claude plugin installed in Cowork and Claude Code                                                                                                  |
| Service                     | Python 3.12; every 15 minutes on Windows Task Scheduler, a macOS launch agent, or a Linux systemd timer, with catch-up after sleep                     |
| Facts                       | One SQLite file                                                                                                                                        |
| Search                      | A local index built at ingestion: exact-word (SQLite FTS5) plus meaning (a 65 MB embedding model run by Oso itself), queried through one Oso tool      |
| Canvas                      | Calendar feed; REST API with a token where allowed                                                                                                     |
| reMarkable (optional)       | Built-in USB web interface: notebooks downloaded as PDFs when plugged in, pages rendered to PNG, transcribed by a Claude Code run on the laptop        |
| Office, LibreOffice, PDF    | MarkItDown; LibreOffice headless for OpenDocument and legacy formats; pointer notes for Google Docs                                                    |
| Google                      | Built-in Drive, Gmail, and Calendar connectors for Claude; the service writes urgent changes to its own Oso calendar directly through the Calendar API |
| Browser                     | Claude in Chrome                                                                                                                                       |
| Secrets                     | The operating system's credential store (Windows Credential Manager, macOS Keychain, Linux Secret Service)                                             |

## Privacy and integrity

Course content reaches Anthropic only when the student asks Cowork or Claude Code something, under the consumer terms of their subscription. The account's data-use setting is reviewed and set deliberately at install. The cloud briefing reads only `Today.md` and what the briefing needs. Logs hold no credentials and no note content. Export is copying a folder; wipe is deleting it. The tutor teaches and checks work; it never produces submittable answers, and each course's AI policy is raised whenever it forbids what was asked.

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

| Risk                                                 | Mitigation                                                                                                                                           |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pro usage limits bind during exam weeks              | Measure in Phase 1; move transcription to a local vision model; upgrade to Max                                                                       |
| The cloud briefing task cannot reach the laptop      | The service writes the day's facts into the vault, Drive syncs it, the task reads it there; a local Claude Code run is the fallback                  |
| Vault sync conflicts between Drive and Obsidian      | The service writes only to its own Oso folder, generated files, and folders it fills                                                                 |
| Four apps feel like tool sprawl                      | Cowork is the only place to ask and Obsidian the only place to write; the service, connectors, and plugin are invisible                              |
| Handwriting transcription misreads equations         | Page image linked from every transcript, confidence shown, corrections made in place; test on real handwriting in Phase 2                            |
| School disables Canvas tokens                        | The calendar feed is the primary path and cannot be blocked; the token only adds grades and files                                                    |
| Subscription terms change                            | Oso never calls a model itself; all model use is inside Claude products. Re-check the terms each semester                                            |
| The tutor is confidently wrong on technical material | Citations required, decline on empty retrieval, and a small per-course set of solved problems to spot-check against                                  |
| Academic-integrity concerns                          | Per-course AI policy captured and displayed; tutor teaches and checks rather than answers; nothing is ever submitted                                 |
| It breaks mid-semester with nobody maintaining it    | Problems appear in the briefing in plain language; a self-service health check repairs the common failures; the fix for anything else is in the repo |
| Scope creep                                          | Ship Phase 1 and use it for two weeks before starting Phase 2                                                                                        |
