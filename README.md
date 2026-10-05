# Oso

A study assistant for college students that keeps track of what is due and helps them learn from their own notes.

Oso is assembled from three things: an Obsidian vault that holds everything the student reads and writes, Claude on a Pro subscription (Cowork for everyday use, Claude Code for installation) for intelligence, and a small Python service on the student's laptop that pulls Canvas and the reMarkable tablet, keeps the deadline and grade database, and notices when something changes. There is no server, no API account, and nobody administering it. A student installs it once and owns it.

What it does:

- One trusted list of every deadline, exam, and grade weight across all courses
- A morning briefing on the phone saying what to do today and why
- Alerts on the calendar when a due date moves or something new is posted
- A tutor that answers from the student's own notes, with a citation on every answer
- Study guides, practice tests, and flashcards scoped to each exam
- Handwritten pages, clipped web pages, and course files captured without exporting anything

See [docs/spec.md](docs/spec.md) for the full description and [docs/plan.md](docs/plan.md) for the build plan.

## Install

You need: a Claude Pro subscription with the Claude desktop app, Claude Code, Obsidian, and Google Drive for Desktop. Create a vault folder inside your Google Drive so your phone and Claude's scheduled tasks can see it.

**Windows** (PowerShell, from the cloned repo):

```
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Vault "C:\Users\you\My Drive\Vault"
```

**Linux or macOS**:

```
./install.sh "/path/to/My Drive/Vault"
```

The installer sets up the service, asks for your Canvas Calendar Feed URL (in Canvas: Calendar, then Calendar Feed), schedules an hourly sync, and runs a health check. Run `oso doctor` any time something looks wrong.

Then install the plugin so Claude can use Oso's tools and skills:

- **Claude Code**: `claude plugin install ./plugin` from the repo folder.
- **Cowork**: zip the `plugin` folder and add it in the Claude desktop app's plugin settings, or add this GitHub repo as a plugin source.

Finally, in Cowork or Claude Code, drop a syllabus into the vault's `Inbox` and ask Oso to set up the course.

## Daily use

- **Morning briefing**: in Cowork, create a scheduled task for each morning that runs the `oso-briefing` skill. It reads `Today.md` from the vault through Google Drive and shows up in the Claude app on your phone.
- **Alerts**: create a second scheduled task every few hours that runs `oso-alerts`; it puts moved due dates and rescheduled exams on your Oso calendar.
- **Handwriting**: on the reMarkable, send a notebook to Google Drive into the vault's `Inbox/Handwriting` folder. The next sync queues the pages; run the `oso-transcribe` skill in Claude Code to turn them into notes.
- **Studying**: ask Cowork anything. The explain, study guide, quiz, summarize, check, flashcards, grades, and plan skills all work from your own notes and cite them.

## Commands

```
oso sync              pull every source and rewrite Today.md and Dashboard.md
oso doctor [--fix]    check the installation and explain anything wrong
oso add-course        register a course by hand
oso set-drive-folder  mirror a shared Google Drive folder into a course
oso install-task      schedule the hourly sync
```

## License

MIT. See [LICENSE](LICENSE).
