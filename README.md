<img src="service/oso/assets/oso.png" alt="Oso" width="240">

Oso is a study assistant and personal assistant for college students. It tracks every deadline, exam, and grade weight across your classes, keeps your classes and tasks on your phone, sends a short briefing each morning, and flags changes like a moved due date or a canceled class. When you study, it works from your own notes and course materials: it explains topics, writes study guides and practice tests, and checks your work, citing the note behind every answer.

Oso combines three parts:

- **Obsidian**, a free notes app, holds everything you read and write.
- **Claude**, on a Pro subscription, does the reasoning. You talk to Oso through the Claude app, on your computer or your phone.
- **The Oso service**, a small program on your computer, pulls in Canvas, your school email, and GroupMe, keeps your deadlines, classes, and tasks, and watches for changes.

There is no Oso server. Your notes stay on your computer and in your own Google Drive, and reach Claude only when you ask it something.

## Get started

Setup takes about an hour, most of it installing and signing in to apps. Follow the **[install guide](docs/install.md)**, then read **[Getting the Most Out of Oso](docs/getting-the-most-out-of-oso.md)** for how to use chats, commands, and Oso's study tools well.

## What Oso does

### Your day

- **[The morning briefing](docs/features/morning-briefing.md)**: a short rundown in the Claude app on your phone each morning: what's due, what changed, your classes, your tasks, and what to focus on.
- **[Deadlines and alerts](docs/features/deadlines-and-alerts.md)**: one list of every assignment, quiz, and exam from Canvas and your syllabi. Urgent changes, like a moved due date, go straight onto your calendar.
- **[Class schedule](docs/features/class-schedule.md)**: your classes on your calendar, kept current when an instructor cancels or moves one.
- **[School messages](docs/features/school-messages.md)**: Oso reads your school email, GroupMe (including the event flyers posted as pictures), and Canvas announcements for what affects your schedule or what you have to do, so you don't have to.
- **[Saved pages](docs/features/saved-pages.md)**: keep the web pages you check for everyday things, like dining hall hours, the gym, or your church's events, and Claude starts there when you ask.
- **[Tasks](docs/features/tasks.md)**: a checklist for everything that isn't coursework (laundry, an oil change, registering to vote), on your phone in Google Tasks, plus reminders like "swing by the mail room after class".

### Studying

- **[Studying with Oso](docs/features/studying.md)**: explanations, summaries, study guides, practice tests in a timed quiz window, checks of your own work, flashcards, and study plans, all from your own course materials.
- **[Where you stand](docs/features/where-you-stand.md)**: Oso tracks each topic from your actual results, tells you honestly where you're behind, and warns you when an exam is close and you aren't ready.
- **[Grades](docs/features/grades.md)**: every class's grade side by side in the Oso window, lowest first, with the work pulling each one down.
- **[Textbooks](docs/features/textbooks.md)**: put your textbook in the course folder and Claude cites it by page, and checks your notes against it.
- **[Saving textbook pages from Chrome](docs/features/scrape-page.md)**: `/scrape-page` and a course saves the online textbook page you're reading as part of that course's book, with every diagram written out.
- **[Notes and handwriting](docs/features/notes-and-handwriting.md)**: web clippings filed into the right course, course files made searchable, and handwritten notes, scanned or photographed, turned into text.

### Your sources

- **[Canvas](docs/features/canvas.md)**: deadlines from the calendar feed; with a sign-in, also grades, missing work, instructor comments, course files, announcements, and inbox messages.
- **[Instructors' websites](docs/features/instructor-websites.md)**: Oso follows sites where instructors post materials outside Canvas.

### Making it yours

- **[Rules](docs/features/rules.md)**: tell Oso what you want from now on ("give me the briefing as bullet highlights", "when a test date shows up, block three hours to study three days before").
- **[Your own commands](docs/features/your-own-commands.md)**: the instructions behind each Oso command are notes you can edit.
- **[Feedback](docs/features/feedback.md)**: tell Claude what's broken or what you wish Oso did, and it reaches whoever builds Oso.

### Keeping it running

- **[Looking after Oso](docs/features/looking-after-oso.md)**: the Oso window, status checks, updates, backups, settings, and the end of a semester.

## Where things live in your vault

- `Courses/<term>/<course>/`: one folder per class, grouped by semester (for example `Courses/2026 Fall/Calculus II/`), holding its syllabus, notes, readings, books, and anything Oso pulls in.
- `Clippings/`: where the Web Clipper saves web pages until Oso files them.
- `Today.md` and `Dashboard.md`: written by Oso on every check; don't edit them.
- `Oso/`: Oso's own files, including your rules and the instructions behind each command. You can ignore it.

## Help

- **[When something's wrong](docs/troubleshooting.md)**: ask Claude _"is Oso OK?"_ first; the guide covers the common problems.
- **[Commands](docs/commands.md)**: the command-window commands, for reference.

## For developers

The design is in [docs/spec.md](docs/spec.md). The service is in `service/`, the Claude plugin in `plugin/`, tests in `tests/`. Run tests with `uv run --extra dev pytest`.

Releases: the **stable** channel installs the highest tag of the form `v1.2.3`. Tag a commit on master (for example `git tag v0.1.0 && git push origin v0.1.0`, or create a release on GitHub) to publish it to stable users. Until the first tag exists, stable follows master.

Every new feature gets a line in the list above and its own page in `docs/features/`.

## License

MIT. See [LICENSE](LICENSE).
