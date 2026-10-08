# Oso

Oso is a study assistant. It tracks every deadline, exam, and grade weight across your classes, sends a short briefing to your phone each morning, and flags changes like a moved due date. When you study, it works from your own notes and course materials: it explains topics, writes study guides and practice tests, and checks your work, citing the note behind every answer.

Oso combines three parts:

- **Obsidian**, a free notes app, holds everything you read and write.
- **Claude**, on a Pro subscription, does the reasoning.
- **The Oso service**, a small program on your computer, pulls in Canvas and your reMarkable tablet, keeps the deadline list, and watches for changes.

There is no Oso server. Your notes stay on your computer and in your own Google Drive, and reach Claude only when you ask it something.

## How Oso works, at a glance

**What happens on its own.** Files you put in your course folders (notes, scans, handouts, books, clippings) are taken in within about half a minute of arriving. Every 15 minutes Oso also checks Canvas for new or changed deadlines, catches any files it missed, makes searchable text copies of documents, and updates `Today.md` (what's due soon) and `Dashboard.md` (everything) in your vault. Urgent changes, like a moved due date, go straight onto an **Oso** calendar in Google Calendar. Each morning a briefing appears in the Claude app on your phone.

**Where things live in your vault.**

- `Courses/<term>/<course>/`: one folder per class, grouped by semester (for example `Courses/2026 Fall/Calculus II/`), holding its syllabus, notes, readings, and anything Oso pulls in. Courses never move.
- `Courses/<term>/<course>/Handwriting/`: where scans of paper notes go.
- `Clippings/`: where the Obsidian Web Clipper saves web pages, including syllabi before a course is set up.
- `Oso/`: Oso's own files, including the instructions behind each Oso command (see below). You can ignore it.

**Asking Claude.** Start your chats inside the Cowork project that has your vault attached (step 3.5). Ask in plain words: "What's due this week?", "Summarize Tuesday's physics notes in three sentences", "Quiz me on chapter 4", "Explain the chain rule from my notes." Answers come back in the chat at the length you ask for. Claude saves a file only when you ask, except flashcards, which have to live in the vault for Obsidian to review them.

**Quizzes and practice tests.** Ask Claude to quiz you, and the quiz opens in an Oso window on your computer: one question at a time, timed, with the answers hidden until you submit. Multiple choice is graded on the spot. For worked problems, write each answer on paper or the reMarkable on a page labeled with the question number in the top corner, and add the pages when the window asks (pull them from the plugged-in tablet, or pick a scan or photo). Then tell Claude you're done, and it grades the rest. `oso quiz` reopens a quiz you closed before submitting.

**Adding a course.** Clip the syllabus with the Web Clipper, then type `/create-course <course name>` in a chat. Claude shows every date, exam, and grade weight it found; nothing is saved until you confirm. It then creates the course folder and files the syllabus inside it.

**Adding notes and files.** Scan paper notes into that course's `Handwriting` folder, then run `oso transcribe` in your command window to turn them into searchable notes in the course's `Notes` folder. Drop any other course document into the course folder; Oso makes a text copy on its next check. Scans saved anywhere outside a course folder are ignored.

**Canvas.** If you connect Canvas (see Part 5), Oso also reads your grades, scores, missing work, and instructor comments. New grades and comments show up in the briefing, missing work is flagged, your real graded work counts toward your topic ratings, and the exam warnings say things like "your homework on its topics averages 64%" and offer a study plan and practice test.

**Search.** Oso indexes everything in your course folders on each check, so Claude can find the right passage across your current classes in a fraction of a second, even when your question uses different words than your notes.

**When a semester ends.** Tell Claude to mark a course finished (your briefing suggests it once a course has had nothing due for two weeks). It disappears from the briefing, deadlines, and everyday searches, but stays in place and can still be searched by name. When a new course builds on an old one, like Calculus III on Calculus II, `/create-course` offers to relate them, and searches in the new course then include the old course's notes.

**What Oso learns about you.** Every quiz and every check of your own work is recorded: each question's topic, whether you got it right, the kind of mistake, how long it took, and whether you needed a hint. Claude also quietly notes what you show in study conversations: when you're confused, a specific wrong idea you hold, explaining something correctly in your own words, how you say you learn best, and the grades you're aiming for. From all of it, Oso works out where each topic stands (untested, needs focus, explained but not yet shown, practicing, solid, or maintaining) and what to do next, aims explanations, quizzes, study guides, and the study plan at it, eases off once a topic is solid, and warns you in the morning briefing when an exam is close and you aren't ready. Nothing you say in conversation can make a topic solid by itself: only results can.

**Honest, not flattering.** Claude can't declare a topic solid or a grade good; Oso computes those from evidence, and Claude reports them as they are, gaps first, with the evidence for anything positive. Every question Claude will grade has its grading criteria written before you answer. If you think a grade is wrong, tell Claude and make your case: it looks at your answer fresh against the criteria and changes the grade, up or down, only if the answer supports it. If your practice scores run well above your real graded work on the same topics, the briefing says so and practice gets harder.

Each Sunday, once there are a couple of weeks of results, Claude writes a short note on how you practice: how early you start before exams, whether you retest what you missed, and where your practice goes. Everything is in `Oso/Profile/` in your vault, one note per course (each topic's stage, next step, and the dated trail behind it) plus `Habits.md` and `How I learn.md`; the raw records stay in Oso's database on your computer, and `oso profile --raw` lists them. If a grade, a rating, or a note is wrong, tell Claude ("question 3 on my last physics quiz was right", "I wasn't confused about that"); it confirms with you and fixes the record, and a grade changes only if the grading criteria support it. To throw away a whole quiz, such as a test run, tell Claude "delete that quiz" (or run `oso profile --delete-quiz N`). `oso fresh-start` clears all of it.

**Making commands your own.** The instructions Claude follows for each command (summarize, quiz, study guide, and the rest) are notes you can edit in `Oso/Skills/`. If Oso later ships a new version of one you changed, your briefing tells you, and Claude walks you through keeping yours, taking the new one, or combining them. `oso reset-skills` puts Oso's versions back.

**Looking after Oso.** Everything is done from the Claude app. Say *"open my settings"* and the Oso window opens on your laptop: a status panel that says in plain words what is fine and what needs attention, with a button beside anything that needs doing (update, sign in to Canvas, sync, back up), and your settings on a second tab. Or just ask: *"Oso status"*, *"is Oso OK?"*, *"update Oso"*, *"sync now"*, *"back up now"*. The same window is in your Start menu (Applications on a Mac) as **Oso**, and on Windows **Ctrl+Alt+O** opens it from anywhere.

**Keeping Oso up to date.** When a new version is out, your briefing says so. Say *"update Oso"* in the Claude app (or click **Update Oso** in the Oso window), wait about a minute, and restart the Claude app.

**Instructors' websites.** If an instructor posts materials on their own site, tell Claude ("Dr. Lee posts physics materials at …"), or mention it during `/create-course`. Oso checks the site a few times a day, saves new and changed pages and the documents they link to (PDFs, slides, worksheets) into the course's `Web` folder, where they're searchable like anything else, and the briefing lists what's new. Sites that need a sign-in can't be followed; Oso says so. `oso sites` shows what's followed.

**Backups.** If you set a backup folder in the Oso window's Settings tab (a network share, an external drive, any folder), Oso copies your vault and its records there every night, keeping deleted files for 30 days. Say *"back up now"* to Claude (or click **Back up now**) to run one now; `oso restore --from <folder>` brings everything back on a new computer.

**When something seems wrong.** Ask Claude *"is Oso OK?"*, or open the Oso window: it checks every part of Oso, fixes what it can, and says in plain words what's left. Part 6 below lists common problems.

Oso runs on Windows, macOS, and Linux. Installation instructions follow. Setup takes about an hour, most of it installing and signing in to apps. Do the sections in order; where a step differs by platform, the differences are listed.

---

## Part 1: Accounts and apps

### 1.1 Google account

You need a Google account (a Gmail address). Oso uses Google Drive to carry your notes to your phone and to Claude, and Google Calendar for alerts. If your school gives you a Google account, that works too.

### 1.2 Claude Pro

1. Go to [claude.ai](https://claude.ai) and sign in or create an account.
2. Upgrade to the **Pro** plan. Oso needs Pro for Cowork, scheduled tasks, and Claude Code.
3. In Settings, find the **privacy** or **data** section and turn off the option that lets Claude use your conversations to improve its models.

### 1.3 Claude on your computer and phone

Cowork is the part of Claude that works with folders on your computer and runs scheduled tasks. You reach it through the Claude desktop app, or through claude.ai in a browser.

- **Windows and macOS**: download the Claude desktop app from [claude.ai/download](https://claude.ai/download), install it, and sign in. Open **Cowork** in the sidebar once so it is set up.
- **Linux**: there is no desktop app. Use Cowork at [claude.ai](https://claude.ai) in your browser; it works with your vault through Google Drive. Claude Code (step 1.6) runs on Linux.

On your phone, install the Claude app from the App Store or Google Play and sign in with the same account. The morning briefing arrives here.

### 1.4 Google Drive on your computer

Your vault lives in a folder that Google Drive keeps in sync, so your phone and Claude's scheduled tasks see the same notes your computer does.

- **Windows and macOS**: download Google Drive for Desktop from [google.com/drive/download](https://www.google.com/drive/download/), install it, and sign in. Either **Stream files** or **Mirror files** works. You will then have a Drive folder on your computer: on Windows usually `G:\My Drive` or `C:\Users\<you>\My Drive`; on macOS `~/Library/CloudStorage/GoogleDrive-<your email>/My Drive`.
- **Linux**: Google does not make a Drive client for Linux. Install [rclone](https://rclone.org/install/), run `rclone config` to add a Google Drive remote named `gdrive`, and make a local folder for your vault (for example `~/Vault`). The installer in Part 2 offers to keep that folder in sync with Drive every 15 minutes.

### 1.5 Obsidian

1. Download Obsidian from [obsidian.md](https://obsidian.md) and install it. It is free and runs on all three platforms.
2. Open Obsidian and choose **Create new vault**. Name it `Vault` (or anything you like) and, for the location, pick a folder **inside your Drive folder** from step 1.4 (on Linux, the folder you chose for rclone). This is how Claude, including the Claude app on your phone, sees your notes.
3. Turn on community plugins: open **Settings**, then **Community plugins**, and click **Turn on community plugins**.

**Web Clipper** (saving web pages and papers into your vault):

1. Install the Obsidian Web Clipper in your browser from [obsidian.md/clipper](https://obsidian.md/clipper). When it asks for a vault, pick the one you just made.
2. Give it Oso's template so clips land in the right place with the right properties: click the clipper's icon, open its **Settings** (the gear), go to **Templates**, choose **Import**, and pick Oso's template file. Download it first from [this link](https://raw.githubusercontent.com/loganbecket/oso/master/obsidian/web-clipper-template.json) (right-click the page and choose **Save as** if it opens as text). If import is not offered, make a new template named `Oso` by hand: note location `Clippings`, note name `{{title}}`, and properties `type` = `reading`, `book` (empty), `page` (empty), `source` = `{{url}}`, `author` = `{{author}}`, `clipped` = `{{date}}`.
3. To clip a page: click the clipper icon, pick the **Oso** template, and save. There's no course to type: within about half a minute Oso works out which course the page belongs to and files it into that course's `Readings` folder, comparing it with each course's notes and materials on your computer (no Claude usage). When it can't tell, it leaves the page in `Clippings` and the morning briefing asks you which course; tell Claude, or say it belongs to none. If Oso guesses wrong, tell Claude ("that article was for history") and it moves it. A syllabus is never filed this way: it waits in `Clippings` for `/create-course`.
4. **Pages from an online textbook:** paste the book's title in the `book` box (part of the title is enough, as long as it's the same each time) and type the page number in `page`. The page joins that book, in the course whose syllabus names it; every later page of the book follows. If a book lands in the wrong course, tell Claude and the whole book moves.
5. If you set up the clipper before Oso version 0.10, import the template once more to get the version without the course box (the old one keeps working meanwhile).

**Spaced Repetition** (flashcards):

1. In **Settings**, **Community plugins**, click **Browse**, search for **Spaced Repetition**, click **Install**, then **Enable**.
2. Oso's flashcard skill writes cards into `Courses/<term>/<course>/Notes/` tagged for this plugin. To review, open the command palette (Ctrl+P, or Cmd+P on a Mac), run **Spaced Repetition: Review flashcards**, and rate each card. The plugin schedules the next time you see it.

**Optional but useful:**

- **Dataview** (community plugin): lets a note show a live list of other notes, for example every reading for a course or every page Oso flagged as low confidence. Install and enable it the same way; the course page Oso creates includes a query that uses it.

### 1.6 Claude Code

Claude Code is Claude in a command window. You use it for installing Oso and for transcribing your handwritten notes. Install it by following the instructions at [claude.ai/code](https://claude.ai/code) for your platform, then sign in with the same Claude account.

### 1.7 A command window

A few steps below use a command window. Open one now:

- **Windows**: press the Windows key, type `PowerShell`, and press Enter.
- **macOS**: open **Terminal** (in Applications, Utilities).
- **Linux**: open a terminal.

---

## Part 2: Install the Oso service

### 2.1 Get your Canvas calendar feed

Canvas is your school's course website where assignments and grades are posted. Every Canvas account has a private calendar feed that Oso reads.

1. Sign in to Canvas in your browser.
2. Click **Calendar** in the left menu.
3. On the right side of the calendar page, click **Calendar Feed**.
4. A box appears with a long web address starting with `https://` and ending in `.ics`. Copy the whole thing. Treat it like a password: anyone with it can see your calendar.

### 2.2 Run the installer

If the Claude app is open, quit it first (on Windows, also from the system tray). Then copy the lines for your platform into the command window from step 1.7, one at a time, pressing Enter after each.

- **Windows** (PowerShell), two lines:

  ```
  irm https://raw.githubusercontent.com/loganbecket/oso/master/install.ps1 -OutFile $env:TEMP\oso-install.ps1
  ```

  ```
  powershell -ExecutionPolicy Bypass -File $env:TEMP\oso-install.ps1
  ```

- **macOS and Linux**:

  ```
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/loganbecket/oso/master/install.sh)"
  ```

The installer:

- installs a small helper called `uv` if you do not have it, then uses it to download and install the newest Oso release (on Windows it first stops any copy of Oso that is already running, so running it again is always safe)
- asks where your vault is (the folder from step 1.5), your time zone (US Eastern unless you type another, such as `America/Chicago`), and the Canvas calendar feed address from step 2.1 (right-click or Cmd-V to paste, then Enter)
- adds the starting folders to your vault
- schedules Oso to check for changes every 15 minutes, even when the computer is asleep (Windows Task Scheduler, a macOS launch agent, or a Linux systemd timer)
- on Linux, offers to keep the vault in sync with Google Drive through rclone
- runs a first sync and a health check

When it finishes it prints a short report. Lines starting with `ok` are fine. Anything marked `WARN` or `FAIL` says what to do in plain words.

**Then close the command window and open a new one.** The `oso` command only works in windows opened after the installer finishes; in the old window it reports that `oso` is not recognized.

### 2.3 Check it worked

Open your vault in Obsidian. There is now a file called `Today.md`. It lists what is due, what changed, and whether Canvas is connected. It is rewritten every 15 minutes; do not edit it.

If `Today.md` is missing or Canvas shows as not connected, run `oso doctor` in your command window and follow what it says.

---

## Part 3: Connect Claude to Oso

### 3.1 Connect Google to Claude

In the Claude app (or claude.ai), open **Settings**, then **Connectors**. Connect **Google Drive**, **Google Calendar**, and **Gmail**, signing in with your Google account each time. Drive is required; Calendar lets Claude put study blocks on your calendar; Gmail is optional.

### 3.2 Connect the Oso calendar

Oso puts urgent changes (a moved due date, a rescheduled exam, a new graded item due soon) on a Google calendar of its own, with reminders, within minutes of noticing them. It does this itself, without Claude, so it costs none of your Claude usage. It can only touch calendars it created, never your others.

Google requires a one-time setup to let a program like Oso do this. It takes about ten minutes, and the file it produces can be reused on any computer.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with your Google account. Accept the terms if asked.
2. At the top, click the project picker and choose **New project**. Name it `Oso` and click **Create**. Make sure the new project is selected.
3. In the search bar, type **Google Calendar API**, open it, and click **Enable**.
4. In the search bar, type **Google Auth Platform** and open it. Click **Get started**. App name `Oso`; your email as the support and contact email; audience **External**. Finish the steps and click **Create**.
5. In the left menu, open **Audience** and click **Publish app**, then confirm. This keeps the connection from expiring every seven days.
6. In the left menu, open **Clients**, click **Create client**, choose application type **Desktop app**, name it `Oso`, and click **Create**. Click **Download JSON** and save the file somewhere you can find it.
7. Run `oso connect-calendar --client-file "<path to the downloaded file>"` in your command window, or click **Connect Google Calendar** in the Oso window and pick the file.
8. A browser window opens. Sign in, and if Google says the app is not verified, click **Advanced**, then **Go to Oso**. Allow access.

Oso then creates a calendar named **Oso** in your Google Calendar. To stop it, run `oso disconnect-calendar`; the calendar stays until you delete it.

Without this step, urgent changes still appear in `Today.md`, in your morning briefing, and in `Oso/Alerts.md`; they just don't reach your calendar.

### 3.3 Connect school email and GroupMe

Most of what competes for your time arrives outside Canvas: an instructor's email moving a deadline, the registrar saying registration opens Monday, a GroupMe message moving tonight's meeting to the soccer fields. With these connected, Oso reads them on every check, has Claude pick out what matters (a deadline, an event, something you need to do, or a change to one of them), and keeps those facts with your deadlines. Events go on the Oso calendar, marked with where they came from, and the morning briefing weighs everything together: "You have an important test tomorrow in a class where your grade needs work, and your practice says you're not ready. Consider skipping tonight's mixer."

What is kept is the facts, with a link back to the message. Message text is never copied into your vault, and Oso never sends, deletes, or changes anything in your email or GroupMe. Ads, social-network notices, and Canvas's own notification emails are set aside without Claude reading them.

**School email.** Oso reads one Gmail account: the one your school email is forwarded to. If your school email isn't forwarded there yet, add a rule in your school email that forwards everything to that Gmail address.

1. In the Google Cloud project from step 3.2, search for **Gmail API**, open it, and click **Enable**.
2. Say *"open my settings"* in the Claude app (or press Ctrl+Alt+O), open the **Actions** tab, and click **Connect email**. Or run `oso connect-email` in your command window.
3. A browser window opens. Sign in with the Gmail account your school email is forwarded to. If Google says the app is not verified, click **Advanced**, then **Go to Oso**, and allow Oso to read your email.

Forwarded messages are unwrapped, so Oso sees who originally sent each one.

**GroupMe** (optional):

1. Go to [dev.groupme.com](https://dev.groupme.com) and sign in with your GroupMe account.
2. Click **Access Token** at the top right and copy it.
3. In the Oso window's **Actions** tab, click **Connect GroupMe** and paste it. Or run `oso connect-groupme`.

Every group is read until you mute it: untick it on the Settings tab, or tell Claude "stop reading the memes group". To stop reading an email sender or mailing list, add it under **Email senders to ignore** on the Settings tab, or tell Claude. Reading messages uses some of your Claude plan; set a daily limit on the Settings tab if it uses too much (no limit by default).

You can also tell Claude about things that reach your personal email or come up in conversation: "add Saturday's tailgate, noon at the stadium" puts it on the Oso calendar.

### 3.4 Install the Oso plugin

The plugin is the set of instructions that teach Claude how to use Oso.

**In Cowork:**

1. In the sidebar, open **Customize**, then **Plugins**.
2. Select **Add marketplace** and enter `loganbecket/oso`.
3. The Oso plugin appears. Click **Install**. Then, on the same Plugins page, open the Oso marketplace's menu and turn on **Sync automatically**, so the plugin keeps itself up to date and `oso update` is the only update you ever run.
4. Open the installed plugin and go to its **Connectors** tab. The **oso** connector is listed as "Runs in each session"; there is nothing to click, and it starts on its own in every new chat. This is what lets Claude read your deadlines and notes. Do not use **Add custom connector**; that is only for connectors hosted on the internet. (On Linux, where Cowork runs in the browser, this connector cannot reach your computer; use Claude Code for anything that needs it, and Cowork for the briefing and questions over the vault in Drive.)

**In Claude Code:** a plugin installed in Cowork is saved to your Claude account, so Claude Code has it too. On Linux, where there is no desktop app, start Claude Code (`claude` in the command window) and type these two lines:

```
/plugin marketplace add loganbecket/oso
/plugin install oso@oso
```

### 3.5 Set up your courses

1. In Cowork, click **Projects** in the sidebar and create a project named `School`. When it asks for a folder, pick your vault folder. Start every study chat inside this project so Claude can see your notes. (In Claude Code, start `claude` from inside the vault folder instead.)
2. Open the course syllabus in your browser and clip it with the Obsidian Web Clipper. It lands in your vault's `Clippings` folder and stays there for course setup. A syllabus PDF dragged into `Clippings` through Obsidian works too.
3. In a chat in the School project, type `/create-course` followed by the course name, for example `/create-course Intro to Engineering`.
4. Claude finds the syllabus, reads it, and shows you every date, exam, and grade weight it found. Check them, correct anything wrong, and confirm. Only then does it create the course folder, move the syllabus into it as `Syllabus`, and save the dates.
5. Repeat for each course.

### 3.6 Schedule the morning briefing

In Cowork, create a scheduled task that runs every day at the time you wake up, with the instruction *"Run the oso-briefing skill."* It reads `Today.md` from your vault through Google Drive, and the result appears in the Claude app on your phone. It runs in Claude's cloud, so it works even when your computer is off.

---

## Part 4: Your reMarkable tablet

Oso pulls your handwritten notes straight off the tablet over the USB cable. No reMarkable account or subscription is needed, and only your coursework comes over.

The rule is simple: **a folder on the tablet with the same name as a course folder in your vault belongs to that course.** When you set up a course in Part 3, Oso created a folder for it in the vault, for example `Courses/2026 Fall/Physics`. Make a folder called `Physics` on the tablet and keep that class's notebooks in it. Every notebook in that folder, including any sub-folders you make, is copied into `Courses/2026 Fall/Physics/Handwriting` in your vault. Notebooks anywhere else on the tablet, like a journal or a to-do list, are never touched.

1. On the tablet, open **Settings**, then **Storage**, and turn on **USB web interface**.
2. On the tablet, make one folder per course, named exactly as the course folder in your vault (capital letters do not matter). If you would rather keep them together, put them all inside one folder such as `School` and run `oso set-remarkable-folder School` once in your command window.
3. Plug the tablet into your computer with its USB cable. It appears as a small network device; the first time can take a minute. On Windows, if asked about a new network, choose **Private**. On macOS and Linux nothing needs to be done.
4. The next time Oso syncs (within 15 minutes, or run `oso sync`), it copies any notebook you changed. Leave it plugged in for a few minutes; charging it at your desk is enough.
5. Oso turns the pages into notes you can search on its own, in the background. To have it done right away, run `oso transcribe` in your command window (or click **Transcribe now** in the Oso window). It sends each page to Claude one at a time, writes the pages out with their equations and a description of every diagram, files the note in the right course, and skips blank pages. Pages it could not read well are listed in your morning briefing. Saying *"Transcribe my handwritten notes"* in Claude Code does the same thing.

**Paper notes** work the same way. Scan them with any phone scanning app (Adobe Scan, for example) and save the PDF to Google Drive inside your vault, in the course's `Handwriting` folder: `Vault/Courses/2026 Fall/Physics/Handwriting`. Drive brings it to your computer, and the next check queues the pages. A photo saved there works too.

**Usage.** Reading handwriting is the heaviest thing Oso asks of your Claude plan. Two settings in the Oso window control it: the picture size for reading handwriting (1200 pixels tall by default; smaller is cheaper, larger reads tiny writing better) and the model used for reading (Sonnet by default, which is accurate and light on usage). A separate setting picks the model for study guides and practice tests (Opus by default, where realism matters most). Two more settings keep everyday questions cheap: a cap on how much of a note Claude reads in one go (12,000 characters by default; set it to 0 to turn the cap off if answers seem to be missing context), and a small instructions file Oso keeps at the top of the vault so Claude Code sessions opened there know the layout without exploring. Which models your plan offers depends on Anthropic; the Claude app shows the current list.

**If the computer does not see the tablet:** make sure the tablet's software is up to date (Settings, General, Software). Older tablet versions used a USB connection type that recent Windows releases dropped.

---

## Part 5: Everyday use

- **Every morning** the briefing is in the Claude app on your phone: due today, due this week, what changed, days until each exam, and what to focus on.
- **Reading online**: click the Web Clipper, choose the Oso template, type the course, save. The note is filed into that course's Readings folder on the next sync.
- **Course files**: anything your professor posts to Canvas (with a Canvas token, see below) or to a shared Google Drive folder is copied into the course folder, and a readable text copy is made next to it so Claude can search it. Word, PowerPoint, Excel, PDF, and LibreOffice files all work; installing LibreOffice (free, [libreoffice.org](https://www.libreoffice.org)) gives the best results for LibreOffice files and older Office formats. Google Docs, Sheets, and Slides stay in Google Drive; Oso leaves a short note with the link, and Claude reads them through its Google Drive connector.
- **Studying**: open Cowork on your vault and ask. Examples:
  - "Explain the chain rule from my notes."
  - "Make a study guide for the physics midterm."
  - "Quiz me on chapter 3."
  - "Here's my attempt at problem 4, where did I go wrong?" (attach a photo)
  - "What do I need on the final to get an A in chemistry?"
  - "Plan my studying for next week and put it on my calendar."
  - "Make flashcards for the vocabulary in lecture 5."
- **Grades**: Oso tracks them if your school allows a Canvas token (below). Otherwise tell Claude a grade and it records it.
- **Something looks wrong**: ask Claude *"is Oso OK?"*, or say *"open my settings"* and look at the status panel. (In a command window, `oso doctor --fix` does the same.)
- **Updating Oso**: when a newer version exists, the morning briefing and `oso doctor` say so. Say *"update Oso"* in the Claude app, click **Update Oso** in the Oso window, or run `oso update` in your command window; it downloads the new version from GitHub, reinstalls the service, and keeps your notes, deadlines, and settings. On Windows the update runs in a new window that shows the installer and closes by itself when it's done; then restart the Claude app. By default Oso follows **stable**, meaning only versions marked as releases. To get every change as soon as it is published, set **Updates** to **latest** in `oso settings`. If a new version causes trouble, `oso update --version v0.1.1` (or any earlier release from v0.1.1 on) goes back to it. Oso comes in two pieces: the service on your computer, which `oso update` replaces, and the plugin inside the Claude app, which only the Claude app can update. With **Sync automatically** on (step 3.4) the plugin updates itself; otherwise click **Check for updates** on the Oso plugin under Customize, Plugins. The plugin rarely changes, since the instructions behind each command come with the service.
- **Search**: on every check Oso indexes your notes and course materials, so Claude can find the right passage across every course in a fraction of a second, by meaning as well as exact words (a question about derivatives finds notes that only say "rate of change"). The first check after installing downloads a small search model (about 65 MB); indexing a large batch of new material can take a few minutes in the background, and later checks only index what changed.
- **Feedback about Oso**: type `/oso-feedback`, or just say what's wrong or what you wish Oso did ("the equations in my quiz don't display right"). Claude asks before passing on anything you didn't send on purpose, then saves it, in your words, in `Oso/Feedback/` in your vault, where it travels with the nightly backup to whoever builds Oso.
- **Rules**: say what you want from now on ("give me the briefing as bullet highlights", "when a new test date shows up, block three hours to study three days before"). Claude asks whether to keep it as a rule, and it's saved in `Oso/Rules/` in your vault. `/oso-rules` lists them and changes, pauses, or deletes one. The briefing says when a rule did something.
- **Making Oso's commands your own**: the instructions behind each Oso command (summarize, quiz, study guide, and the rest) are plain notes in your vault under `Oso/Skills/`. Edit one in Obsidian and Claude follows your version from then on. When Oso updates a command you haven't touched, your copy updates quietly. If you have changed it, your copy is kept, and the briefing tells you a new version is waiting; ask Claude to go through the Oso command updates, and it shows what changed on each side and lets you keep yours, take Oso's, or combine them. To throw away your edits, run `oso reset-skills` (or `oso reset-skills oso-summarize` for just one). Files you add to that folder yourself are never touched.
- **Changing settings**: say *"open my settings"* in the Claude app, open **Oso** from the Start menu, or run `oso settings` in your command window. The Oso window opens on its status panel; the **Settings** tab is where you can change the vault folder, time zone, how often Oso checks for changes (15 minutes by default), what counts as urgent, quiet hours, which courses are muted, the tablet folder, and the Canvas feed or token. **Save and check** applies the change, reschedules the checks if needed, and runs the health check.

### Textbooks

Put each textbook in the course's `Books` folder (for example `Courses/2026 Fall/Physics/Books`), and Oso turns it into notes you and Claude can search, one per chapter, with every page marked by its printed page number. Answers then cite the book ("Serway, ch. 4.2, p. 131"), and when your notes and the book disagree, Claude says so and goes with the book.

- **A PDF or EPUB** (one without copy protection): drop the file in `Books`. Oso reads it on the next check; a big book takes a few checks, and `oso books` shows how far along it is.
- **A scanned book or chapter, or photos of pages**: make a folder for the book with a `Scans` folder inside, `Books/<title>/Scans/`, and put the scans there in order (name them so they sort in page order). Scans you add later join the end of the book. Your computer's built-in text recognition reads the printed text. Pages with handwriting, equations, tables, diagrams, or drawings are read by Claude automatically in the background, with equations kept and drawings described; you never have to ask. This uses some of your Claude plan; if it uses too much, set a daily page limit in `oso settings` (no limit by default).
- **A book you read in a publisher's app or website**: print chapters to PDF and drop them in `Books`; or take screenshots of pages and put them in `Books/<title>/Scans/`; or clip pages with the Web Clipper, filling in `course`, `book` (the book's title), and `page`, and Oso files each clip into that book. Highlights and notes exported from a reader app go in `Books/<title>/Highlights/`; they're kept as your notes, not as the book.

Ask Claude to **check my notes** against the book for a lecture or a chapter: it lists what's wrong, what's missing, and what the book covers that your notes skip, and saves corrections beside your note (never inside it) if you want. Scanned handouts and worksheets anywhere in a course folder are read the same way. Book text stays in your vault. `oso fresh-start` keeps your books and what Oso has read of them.

### Connect Canvas for grades and coursework

The calendar feed only brings in due dates. To let Oso read your grades, scores, missing work, instructor comments, and course materials too (every file and page in each course's modules, organized by module under `Canvas/Modules`), sign in to Canvas once through Oso:

```
oso connect-canvas
```

A small window opens with your school's Canvas sign-in page. Sign in as you normally do, including any two-step check; the window closes by itself once you're in. To skip typing, give Oso your school username and password once (Oso window, Actions tab, **Canvas username and password…**). They're kept in your computer's credential store, never in a file, and the sign-in window fills them in. When Canvas logs you out, Oso then signs in again on its own, out of sight; if your school's two-step check (such as Duo) wants approval, a notification tells you to approve it on your phone. Oso keeps the signed-in session in the credential store and reads your own Canvas pages on every check, never changing anything. (**Sign in to Canvas** in the Oso window opens the window any time.)

Canvas ends sign-ins after a while. When that happens, Oso shows a notification ("Canvas needs you to sign in again"); click it, or run `oso connect-canvas`, and sign in again. Until you do, your briefing says so and due dates keep coming from the calendar feed. `oso canvas --raw` shows what Oso has read, and `oso disconnect-canvas` makes it forget the sign-in.

If your school allows Canvas access tokens, you can use one instead: in Canvas, open **Account**, **Settings**, **+ New Access Token**, then run `oso init --vault "<your vault path>" --canvas-url https://<yourschool>.instructure.com --canvas-token <the token>`.

### Optional: a shared Google Drive folder

If a professor shares a Drive folder of lecture files, find it in your Drive folder on the computer and run:

```
oso set-drive-folder MATH-101-001 "<path to that folder>"
```

(use the course code Oso printed when you set the course up).

---

## Part 6: Problems

| What you see | What to do |
| --- | --- |
| Urgent changes are not reaching my calendar | Run `oso doctor`. If it says Google Calendar is not connected, do step 3.2. If the connection expired, check the Google project is published (step 3.2, point 5) and connect again. |
| The briefing did not arrive | Open the Claude app and check the scheduled task ran. Then check `Today.md` in your vault is from today; if not, run `oso doctor`. |
| `Today.md` says Canvas has not synced in many hours, or deadlines never change | Your computer may have been off. Turn it on and wait a few minutes, or run `oso sync`. If it keeps happening, run `oso doctor --fix`; it recreates the automatic check if it is missing. |
| Canvas says the login was rejected or the address no longer works | Get a fresh calendar feed address (step 2.1) and run `oso init` again with it. |
| `oso` is not recognized as a command | Close the command window and open a new one. If it still fails, run `uv tool update-shell`, then open another new window. |
| Claude says it cannot reach Oso's tools | Run `oso doctor`. If it says `oso-mcp` is missing, run the installer lines again (step 2.2). Then restart the Claude app. |
| Every `oso` command prints `No module named 'oso'`, or an install says `Access is denied` | An update was interrupted while Oso was running. Quit the Claude app and run the installer lines again (step 2.2); your settings and deadlines are kept. |
| `oso install-task` says `Access is denied` | You have a version older than v0.1.1. Run the installer lines again (step 2.2). |
| A handwritten page came out wrong | The original page image is linked at the bottom of the note. Fix the text in Obsidian; Oso never overwrites your edits. |
| The tablet does not sync | Check **USB web interface** is on, the cable is in, and the tablet software is current. Check the notebook is inside a folder named after the course. Run `oso sync` while it is plugged in. |
| I want to start over | Quit the Claude app and run `oso fresh-start`. It deletes everything in the vault (except Obsidian's settings, your textbooks, and your feedback about Oso) and everything Oso has recorded, with no backup, keeps all your settings and connections, and pulls your Canvas deadlines back in. Then set up each course again with `/create-course`. |

## Commands

You rarely need these: the Oso window and the Claude app do the same things. They're here for reference, and for when the Claude app can't reach Oso.

```
oso sync                  pull every source and rewrite Today.md and Dashboard.md
oso doctor [--fix]        check the installation and explain anything wrong
oso health                when each source last synced
oso add-course            register a course by hand
oso set-drive-folder      mirror a shared Google Drive folder into a course
oso set-remarkable-folder the tablet folder that holds the course folders
oso settings              open the Oso window (status and settings)
oso transcribe            turn queued handwritten pages into notes
oso install-task          schedule the sync (every 15 minutes by default)
oso update                install the newest Oso on your update channel
oso update --version V    install an exact earlier version
oso reset-skills [NAME]   put back Oso's version of its commands (all, or the ones named)
oso quiz [N]              reopen a quiz window (the latest one not yet submitted)
oso profile --raw         show every recorded quiz, question by question
oso connect-canvas        sign in to Canvas so Oso can read grades and coursework
oso connect-email         let Oso read the Gmail your school email is forwarded to (read-only)
oso connect-groupme       let Oso read your GroupMe groups
oso canvas --raw          show what Oso has read from Canvas
oso books                 how far Oso has read each textbook (--reprocess TITLE reads one again)
oso sites                 instructor websites Oso follows (--add COURSE URL, --check)
oso backup                back up now (--set-folder PATH sets the backup folder)
oso restore --from PATH   bring the vault and Oso's records back from a backup
oso watch                 take in new files as they arrive (runs on its own from sign-in)
oso fresh-start           start over as if newly installed, keeping your settings (deletes the vault's contents)
oso connect-calendar      let Oso put urgent changes on its own Google calendar
oso disconnect-calendar   stop that and forget the access
```

## For developers

The design is in [docs/spec.md](docs/spec.md). The service is in `service/`, the Claude plugin in `plugin/`, tests in `tests/`. Run tests with `uv run --extra dev pytest`.

Releases: the **stable** channel installs the highest tag of the form `v1.2.3`. Tag a commit on master (for example `git tag v0.1.0 && git push origin v0.1.0`, or create a release on GitHub) to publish it to stable users. Until the first tag exists, stable follows master.

## License

MIT. See [LICENSE](LICENSE).
