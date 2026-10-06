# Oso

Oso is a study assistant. It tracks every deadline, exam, and grade weight across your classes, sends a short briefing to your phone each morning, and flags changes like a moved due date. When you study, it works from your own notes and course materials: it explains topics, writes study guides and practice tests, and checks your work, citing the note behind every answer.

Oso combines three parts:

- **Obsidian**, a free notes app, holds everything you read and write.
- **Claude**, on a Pro subscription, does the reasoning.
- **The Oso service**, a small program on your computer, pulls in Canvas and your reMarkable tablet, keeps the deadline list, and watches for changes.

There is no Oso server. Your notes stay on your computer and in your own Google Drive, and reach Claude only when you ask it something.

## How Oso works, at a glance

**What happens on its own.** Every 15 minutes Oso checks Canvas for new or changed deadlines, picks up new files and scans in your course folders, makes searchable text copies of documents, and updates `Today.md` (what's due soon) and `Dashboard.md` (everything) in your vault. Urgent changes, like a moved due date, go straight onto an **Oso** calendar in Google Calendar. Each morning a briefing appears in the Claude app on your phone.

**Where things live in your vault.**

- `Courses/<term>/<course>/`: one folder per class, grouped by semester (for example `Courses/2026 Fall/Calculus II/`), holding its syllabus, notes, readings, and anything Oso pulls in. Courses never move.
- `Courses/<term>/<course>/Handwriting/`: where scans of paper notes go.
- `Clippings/`: where the Obsidian Web Clipper saves web pages, including syllabi before a course is set up.
- `Oso/`: Oso's own files, including the instructions behind each Oso command (see below). You can ignore it.

**Asking Claude.** Start your chats inside the Cowork project that has your vault attached (step 3.4). Ask in plain words: "What's due this week?", "Summarize Tuesday's physics notes in three sentences", "Quiz me on chapter 4", "Explain the chain rule from my notes." Answers come back in the chat at the length you ask for. Claude saves a file only when you ask, except flashcards, which have to live in the vault for Obsidian to review them.

**Quizzes and practice tests.** Ask Claude to quiz you, and the quiz opens in an Oso window on your computer: one question at a time, timed, with the answers hidden until you submit. Multiple choice is graded on the spot. For worked problems, write each answer on paper or the reMarkable on a page labeled with the question number in the top corner, and add the pages when the window asks (pull them from the plugged-in tablet, or pick a scan or photo). Then tell Claude you're done, and it grades the rest. `oso quiz` reopens a quiz you closed before submitting.

**Adding a course.** Clip the syllabus with the Web Clipper, then type `/create-course <course name>` in a chat. Claude shows every date, exam, and grade weight it found; nothing is saved until you confirm. It then creates the course folder and files the syllabus inside it.

**Adding notes and files.** Scan paper notes into that course's `Handwriting` folder, then run `oso transcribe` in your command window to turn them into searchable notes in the course's `Notes` folder. Drop any other course document into the course folder; Oso makes a text copy on its next check. Scans saved anywhere outside a course folder are ignored.

**Search.** Oso indexes everything in your course folders on each check, so Claude can find the right passage across your current classes in a fraction of a second, even when your question uses different words than your notes.

**When a semester ends.** Tell Claude to mark a course finished (your briefing suggests it once a course has had nothing due for two weeks). It disappears from the briefing, deadlines, and everyday searches, but stays in place and can still be searched by name. When a new course builds on an old one, like Calculus III on Calculus II, `/create-course` offers to relate them, and searches in the new course then include the old course's notes.

**What Oso learns about you.** Every quiz and every check of your own work is recorded: each question's topic, whether you got it right, the kind of mistake, how long it took, and whether you needed a hint. From that, Oso rates each topic in a course as strong, shaky, or not yet tested (a topic you've never been tested on is never assumed known), aims quizzes and study guides at the weak ones, and warns you in the morning briefing when an exam is close and you aren't ready. Each Sunday, once there are a couple of weeks of results, Claude writes a short note on how you practice: how early you start before exams, whether you retest what you missed, and where your practice goes. Everything is in `Oso/Profile/` in your vault, one note per course plus `Habits.md`; the raw records stay in Oso's database on your computer, and `oso profile --raw` lists them. If a grade or a rating is wrong, tell Claude ("question 3 on my last physics quiz was right"); it confirms with you and fixes the record. `oso fresh-start` clears all of it.

**Making commands your own.** The instructions Claude follows for each command (summarize, quiz, study guide, and the rest) are notes you can edit in `Oso/Skills/`. If Oso later ships a new version of one you changed, your briefing tells you, and Claude walks you through keeping yours, taking the new one, or combining them. `oso reset-skills` puts Oso's versions back.

**Keeping Oso up to date.** When a new version is out, your briefing says so. Run `oso update` in your command window, wait about a minute, and restart the Claude app.

**When something seems wrong.** Run `oso doctor` in your command window. It checks every part of Oso and says in plain words what to fix. Part 6 below lists common problems.

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
2. Open Obsidian and choose **Create new vault**. Name it `Vault` (or anything you like) and, for the location, pick a folder **inside your Drive folder** from step 1.4 (on Linux, the folder you chose for rclone). This is how your phone and Claude see your notes.
3. Turn on community plugins: open **Settings**, then **Community plugins**, and click **Turn on community plugins**.

**Web Clipper** (saving web pages and papers into your vault):

1. Install the Obsidian Web Clipper in your browser from [obsidian.md/clipper](https://obsidian.md/clipper). When it asks for a vault, pick the one you just made.
2. Give it Oso's template so clips land in the right place with the right properties: click the clipper's icon, open its **Settings** (the gear), go to **Templates**, choose **Import**, and pick Oso's template file. Download it first from [this link](https://raw.githubusercontent.com/loganbecket/oso/master/obsidian/web-clipper-template.json) (right-click the page and choose **Save as** if it opens as text). If import is not offered, make a new template named `Oso` by hand: note location `Clippings`, note name `{{title}}`, and properties `type` = `reading`, `course` (empty), `source` = `{{url}}`, `author` = `{{author}}`, `clipped` = `{{date}}`.
3. To clip a page: click the clipper icon, pick the **Oso** template, type the course in the `course` box (its name, code, or folder, for example `Physics`), and save. The note goes to `Clippings`; on the next sync Oso moves it into that course's `Readings` folder. Leave `course` empty if it belongs to no class and it stays in `Clippings`.

**Spaced Repetition** (flashcards):

1. In **Settings**, **Community plugins**, click **Browse**, search for **Spaced Repetition**, click **Install**, then **Enable**.
2. Oso's flashcard skill writes cards into `Courses/<term>/<course>/Notes/` tagged for this plugin. To review, open the command palette (Ctrl+P, or Cmd+P on a Mac), run **Spaced Repetition: Review flashcards**, and rate each card. The plugin schedules the next time you see it.
3. On your phone, the Obsidian app with the same plugin reviews the same cards.

**Optional but useful:**

- **Dataview** (community plugin): lets a note show a live list of other notes, for example every reading for a course or every page Oso flagged as low confidence. Install and enable it the same way; the course page Oso creates includes a query that uses it.
- On your phone: install the Obsidian app and open the same vault from Google Drive.

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
7. Run `oso connect-calendar --client-file "<path to the downloaded file>"` in your command window, or click **Connect Google Calendar** in `oso settings` and pick the file.
8. A browser window opens. Sign in, and if Google says the app is not verified, click **Advanced**, then **Go to Oso**. Allow access.

Oso then creates a calendar named **Oso** in your Google Calendar. To stop it, run `oso disconnect-calendar`; the calendar stays until you delete it.

Without this step, urgent changes still appear in `Today.md`, in your morning briefing, and in `Oso/Alerts.md`; they just don't reach your calendar.

### 3.3 Install the Oso plugin

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

### 3.4 Set up your courses

1. In Cowork, click **Projects** in the sidebar and create a project named `School`. When it asks for a folder, pick your vault folder. Start every study chat inside this project so Claude can see your notes. (In Claude Code, start `claude` from inside the vault folder instead.)
2. Open the course syllabus in your browser and clip it with the Obsidian Web Clipper. Leave the course field blank; it lands in your vault's `Clippings` folder. A syllabus PDF dragged into `Clippings` through Obsidian works too.
3. In a chat in the School project, type `/create-course` followed by the course name, for example `/create-course Intro to Engineering`.
4. Claude finds the syllabus, reads it, and shows you every date, exam, and grade weight it found. Check them, correct anything wrong, and confirm. Only then does it create the course folder, move the syllabus into it as `Syllabus`, and save the dates.
5. Repeat for each course.

### 3.5 Schedule the morning briefing

In Cowork, create a scheduled task that runs every day at the time you wake up, with the instruction *"Run the oso-briefing skill."* It reads `Today.md` from your vault through Google Drive, and the result appears in the Claude app on your phone. It runs in Claude's cloud, so it works even when your computer is off.

---

## Part 4: Your reMarkable tablet

Oso pulls your handwritten notes straight off the tablet over the USB cable. No reMarkable account or subscription is needed, and only your coursework comes over.

The rule is simple: **a folder on the tablet with the same name as a course folder in your vault belongs to that course.** When you set up a course in Part 3, Oso created a folder for it in the vault, for example `Courses/2026 Fall/Physics`. Make a folder called `Physics` on the tablet and keep that class's notebooks in it. Every notebook in that folder, including any sub-folders you make, is copied into `Courses/2026 Fall/Physics/Handwriting` in your vault. Notebooks anywhere else on the tablet, like a journal or a to-do list, are never touched.

1. On the tablet, open **Settings**, then **Storage**, and turn on **USB web interface**.
2. On the tablet, make one folder per course, named exactly as the course folder in your vault (capital letters do not matter). If you would rather keep them together, put them all inside one folder such as `School` and run `oso set-remarkable-folder School` once in your command window.
3. Plug the tablet into your computer with its USB cable. It appears as a small network device; the first time can take a minute. On Windows, if asked about a new network, choose **Private**. On macOS and Linux nothing needs to be done.
4. The next time Oso syncs (within 15 minutes, or run `oso sync`), it copies any notebook you changed. Leave it plugged in for a few minutes; charging it at your desk is enough.
5. To turn the pages into notes you can search, run `oso transcribe` in your command window (or click **Transcribe now** in `oso settings`). It sends each page to Claude one at a time, writes the pages out with their equations and a description of every diagram, files the note in the right course, and skips blank pages. Pages it could not read well are listed in your morning briefing. Saying *"Transcribe my handwritten notes"* in Claude Code does the same thing.

**Paper notes** work the same way. Scan them with any phone scanning app (Adobe Scan, for example) and save the PDF to Google Drive inside your vault, in the course's `Handwriting` folder: `Vault/Courses/2026 Fall/Physics/Handwriting`. Drive brings it to your computer, and the next check queues the pages. A photo saved there works too.

**Usage.** Reading handwriting is the heaviest thing Oso asks of your Claude plan. Two settings in `oso settings` control it: the page image size (1200 pixels tall by default; smaller is cheaper, larger reads tiny writing better) and the model used for reading (Sonnet by default, which is accurate and light on usage). A separate setting picks the model for study guides and practice tests (Opus by default, where realism matters most). Two more settings keep everyday questions cheap: a cap on how much of a note Claude reads in one go (12,000 characters by default; set it to 0 to turn the cap off if answers seem to be missing context), and a small instructions file Oso keeps at the top of the vault so Claude Code sessions opened there know the layout without exploring. Which models your plan offers depends on Anthropic; the Claude app shows the current list.

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
- **Something looks wrong**: in Claude Code say *"Run the Oso doctor"*, or in your command window run `oso doctor --fix`.
- **Updating Oso**: when a newer version exists, the morning briefing and `oso doctor` say so. Run `oso update` in your command window (or click **Update Oso** in `oso settings`); it downloads the new version from GitHub, reinstalls the service, and keeps your notes, deadlines, and settings. On Windows the update runs in a new window that shows the installer and closes by itself when it's done; then restart the Claude app. By default Oso follows **stable**, meaning only versions marked as releases. To get every change as soon as it is published, set **Updates** to **latest** in `oso settings`. If a new version causes trouble, `oso update --version v0.1.1` (or any earlier release from v0.1.1 on) goes back to it. Oso comes in two pieces: the service on your computer, which `oso update` replaces, and the plugin inside the Claude app, which only the Claude app can update. With **Sync automatically** on (step 3.3) the plugin updates itself; otherwise click **Check for updates** on the Oso plugin under Customize, Plugins. The plugin rarely changes, since the instructions behind each command come with the service.
- **Search**: on every check Oso indexes your notes and course materials, so Claude can find the right passage across every course in a fraction of a second, by meaning as well as exact words (a question about derivatives finds notes that only say "rate of change"). The first check after installing downloads a small search model (about 65 MB); indexing a large batch of new material can take a few minutes in the background, and later checks only index what changed.
- **Making Oso's commands your own**: the instructions behind each Oso command (summarize, quiz, study guide, and the rest) are plain notes in your vault under `Oso/Skills/`. Edit one in Obsidian and Claude follows your version from then on. When Oso updates a command you haven't touched, your copy updates quietly. If you have changed it, your copy is kept, and the briefing tells you a new version is waiting; ask Claude to go through the Oso command updates, and it shows what changed on each side and lets you keep yours, take Oso's, or combine them. To throw away your edits, run `oso reset-skills` (or `oso reset-skills oso-summarize` for just one). Files you add to that folder yourself are never touched.
- **Changing settings**: run `oso settings` in your command window. A small window opens where you can change the vault folder, time zone, how often Oso checks for changes (15 minutes by default), what counts as urgent, quiet hours, which courses are muted, the tablet folder, and the Canvas feed or token. **Save and check** applies the change, reschedules the checks if needed, and runs the health check.

### Optional: a Canvas token

If your school allows it, a token lets Oso read grades, announcements, and course files from Canvas, not just dates. In Canvas, open **Account**, then **Settings**, scroll to **Approved Integrations**, and click **+ New Access Token**. Name it `Oso`, leave the expiry blank, and copy the token. Then in your command window:

```
oso init --vault "<your vault path>" --canvas-url https://<yourschool>.instructure.com --canvas-token <paste the token>
```

If the **+ New Access Token** button is missing, your school has turned tokens off. The calendar feed still gives Oso every deadline.

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
| `Today.md` says Canvas has not synced in many hours | Your computer may have been off. Turn it on and wait a few minutes, or run `oso sync`. If it keeps happening, run `oso install-task` again. |
| Canvas says the login was rejected or the address no longer works | Get a fresh calendar feed address (step 2.1) and run `oso init` again with it. |
| `oso` is not recognized as a command | Close the command window and open a new one. If it still fails, run `uv tool update-shell`, then open another new window. |
| Claude says it cannot reach Oso's tools | Run `oso doctor`. If it says `oso-mcp` is missing, run the installer lines again (step 2.2). Then restart the Claude app. |
| Every `oso` command prints `No module named 'oso'`, or an install says `Access is denied` | An update was interrupted while Oso was running. Quit the Claude app and run the installer lines again (step 2.2); your settings and deadlines are kept. |
| `oso install-task` says `Access is denied` | You have a version older than v0.1.1. Run the installer lines again (step 2.2). |
| A handwritten page came out wrong | The original page image is linked at the bottom of the note. Fix the text in Obsidian; Oso never overwrites your edits. |
| The tablet does not sync | Check **USB web interface** is on, the cable is in, and the tablet software is current. Check the notebook is inside a folder named after the course. Run `oso sync` while it is plugged in. |
| I want to start over | Quit the Claude app and run `oso fresh-start`. It deletes everything in the vault (except Obsidian's settings) and everything Oso has recorded, with no backup, keeps all your settings and connections, and pulls your Canvas deadlines back in. Then set up each course again with `/create-course`. |

## Commands

```
oso sync                  pull every source and rewrite Today.md and Dashboard.md
oso doctor [--fix]        check the installation and explain anything wrong
oso health                when each source last synced
oso add-course            register a course by hand
oso set-drive-folder      mirror a shared Google Drive folder into a course
oso set-remarkable-folder the tablet folder that holds the course folders
oso settings              open the settings window
oso transcribe            turn queued handwritten pages into notes
oso install-task          schedule the sync (every 15 minutes by default)
oso update                install the newest Oso on your update channel
oso update --version V    install an exact earlier version
oso reset-skills [NAME]   put back Oso's version of its commands (all, or the ones named)
oso quiz [N]              reopen a quiz window (the latest one not yet submitted)
oso profile --raw         show every recorded quiz, question by question
oso fresh-start           start over as if newly installed, keeping your settings (deletes the vault's contents)
oso connect-calendar      let Oso put urgent changes on its own Google calendar
oso disconnect-calendar   stop that and forget the access
```

## For developers

The design is in [docs/spec.md](docs/spec.md) and the build plan in [docs/plan.md](docs/plan.md). The service is in `service/`, the Claude plugin in `plugin/`, tests in `tests/`. Run tests with `uv run --extra dev pytest`.

Releases: the **stable** channel installs the highest tag of the form `v1.2.3`. Tag a commit on master (for example `git tag v0.1.0 && git push origin v0.1.0`, or create a release on GitHub) to publish it to stable users. Until the first tag exists, stable follows master.

## License

MIT. See [LICENSE](LICENSE).
