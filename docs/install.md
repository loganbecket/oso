# Installing Oso

Oso runs on Windows, macOS, and Linux. Setup takes about an hour, most of it installing and signing in to apps. Do the sections in order; where a step differs by platform, the differences are listed.

1. [Accounts and apps](#accounts-and-apps)
2. [Install the Oso service](#install-the-oso-service)
3. [Connect Oso to your accounts](#connect-oso-to-your-accounts)
4. [Install the Oso plugin](#install-the-oso-plugin)
5. [Set up your courses](#set-up-your-courses)
6. [Schedule the morning briefing](#schedule-the-morning-briefing)
7. Optional extras: [Claude in Chrome](#claude-in-chrome), [a shared Google Drive folder](#a-shared-google-drive-folder), [a reMarkable tablet](#your-remarkable-tablet) if you have one

---

## Accounts and apps

### Google account

You need a Google account (a Gmail address). Oso uses Google Drive to carry your notes to your phone and to Claude, Google Calendar for your classes and alerts, and Google Tasks for your task list. If your school gives you a Google account, that works too.

### Claude Pro

1. Go to [claude.ai](https://claude.ai) and sign in or create an account.
2. Upgrade to the **Pro** plan. Oso needs Pro for Cowork, scheduled tasks, and Claude Code.
3. In Settings, find the **privacy** or **data** section and turn off the option that lets Claude use your conversations to improve its models.

### Claude on your computer and phone

Cowork is the part of Claude that works with folders on your computer and runs scheduled tasks. You reach it through the Claude desktop app, or through claude.ai in a browser.

- **Windows and macOS**: download the Claude desktop app from [claude.ai/download](https://claude.ai/download), install it, and sign in. Open **Cowork** in the sidebar once so it is set up.
- **Linux**: there is no desktop app. Use Cowork at [claude.ai](https://claude.ai) in your browser; it works with your vault through Google Drive. Claude Code runs on Linux.

On your phone, install the Claude app from the App Store or Google Play and sign in with the same account. The morning briefing arrives here.

### Google Drive on your computer

Your vault lives in a folder that Google Drive keeps in sync, so your phone and Claude's scheduled tasks see the same notes your computer does.

- **Windows and macOS**: download Google Drive for Desktop from [google.com/drive/download](https://www.google.com/drive/download/), install it, and sign in. Either **Stream files** or **Mirror files** works. You will then have a Drive folder on your computer: on Windows usually `G:\My Drive` or `C:\Users\<you>\My Drive`; on macOS `~/Library/CloudStorage/GoogleDrive-<your email>/My Drive`.
- **Linux**: Google does not make a Drive client for Linux. Install [rclone](https://rclone.org/install/), run `rclone config` to add a Google Drive remote named `gdrive`, and make a local folder for your vault (for example `~/Vault`). The installer offers to keep that folder in sync with Drive every 15 minutes.

### Obsidian

1. Download Obsidian from [obsidian.md](https://obsidian.md) and install it. It is free and runs on all three platforms.
2. Open Obsidian and choose **Create new vault**. Name it `Vault` (or anything you like) and, for the location, pick a folder **inside your Drive folder** (on Linux, the folder you chose for rclone). This is how Claude, including the Claude app on your phone, sees your notes.
3. Turn on community plugins: open **Settings**, then **Community plugins**, and click **Turn on community plugins**.

**Web Clipper** (saving web pages and papers into your vault):

1. Install the Obsidian Web Clipper in your browser from [obsidian.md/clipper](https://obsidian.md/clipper). When it asks for a vault, pick the one you just made.
2. Give it Oso's template: click the clipper's icon, open its **Settings** (the gear), go to **Templates**, choose **Import**, and pick Oso's template file. Download it first from [this link](https://raw.githubusercontent.com/loganbecket/oso/master/obsidian/web-clipper-template.json) (right-click the page and choose **Save as** if it opens as text). If import is not offered, make a new template named `Oso` by hand: note location `Clippings`, note name `{{title}}`, and properties `type` = `reading`, `book` (empty), `page` (empty), `source` = `{{url}}`, `author` = `{{author}}`, `clipped` = `{{date}}`.
3. If you set up the clipper before Oso version 0.10, import the template once more to get the version without the course box.

How clipping works day to day is in [Notes and handwriting](features/notes-and-handwriting.md).

**Spaced Repetition** (flashcards): in **Settings**, **Community plugins**, click **Browse**, search for **Spaced Repetition**, click **Install**, then **Enable**.

**Dataview** (optional): lets a note show a live list of other notes; the course page Oso creates uses it. Install and enable it the same way.

### Claude Code

Claude Code is Claude in a command window. You use it for installing Oso and for transcribing handwritten notes. Install it by following the instructions at [claude.ai/code](https://claude.ai/code) for your platform, then sign in with the same Claude account.

### A command window

A few steps below use a command window. Open one now:

- **Windows**: press the Windows key, type `PowerShell`, and press Enter.
- **macOS**: open **Terminal** (in Applications, Utilities).
- **Linux**: open a terminal.

---

## Install the Oso service

### Get your Canvas calendar feed

Canvas is your school's course website where assignments and grades are posted. Every Canvas account has a private calendar feed that Oso reads.

1. Sign in to Canvas in your browser.
2. Click **Calendar** in the left menu.
3. On the right side of the calendar page, click **Calendar Feed**.
4. A box appears with a long web address starting with `https://` and ending in `.ics`. Copy the whole thing. Treat it like a password: anyone with it can see your calendar.

### Run the installer

If the Claude app is open, quit it first (on Windows, also from the system tray). Then copy the lines for your platform into the command window, one at a time, pressing Enter after each.

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
- asks where your vault is, your time zone (US Eastern unless you type another, such as `America/Chicago`), and the Canvas calendar feed address (right-click or Cmd-V to paste, then Enter)
- adds the starting folders to your vault
- schedules Oso to check for changes every 15 minutes, even when the computer is asleep
- on Linux, offers to keep the vault in sync with Google Drive through rclone
- runs a first sync and a health check

When it finishes it prints a short report. Lines starting with `ok` are fine. Anything marked `WARN` or `FAIL` says what to do in plain words.

**Then close the command window and open a new one.** The `oso` command only works in windows opened after the installer finishes.

### Check it worked

Open your vault in Obsidian. There is now a file called `Today.md`. It lists what is due, what changed, and whether Canvas is connected. It is rewritten every 15 minutes; do not edit it. If it is missing or Canvas shows as not connected, run `oso doctor` and follow what it says.

---

## Connect Oso to your accounts

Most connections are made from the **Oso window**: say *"open my settings"* in the Claude app, press **Ctrl+Alt+O** on Windows, or open **Oso** from the Start menu (Applications on a Mac). Its **Actions** tab has a button for each connection, and its status panel shows a button beside anything not yet connected.

### Google in Claude

In the Claude app (or claude.ai), open **Settings**, then **Connectors**. Connect **Google Drive**, **Google Calendar**, and **Gmail**, signing in with your Google account each time. Drive is required; Calendar lets Claude put study blocks on your calendar; Gmail is optional.

### The Oso calendar

Oso keeps a Google calendar of its own named **Oso**: your classes, urgent changes (a moved due date, a rescheduled exam), events from your messages, and reminders. It can only touch calendars it created, never your others. Google requires a one-time setup to allow this. It takes about ten minutes, and the file it produces is reused for email and Google Tasks below.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with your Google account. Accept the terms if asked.
2. At the top, click the project picker and choose **New project**. Name it `Oso` and click **Create**. Make sure the new project is selected.
3. In the search bar, type **Google Calendar API**, open it, and click **Enable**.
4. In the search bar, type **Google Auth Platform** and open it. Click **Get started**. App name `Oso`; your email as the support and contact email; audience **External**. Finish the steps and click **Create**.
5. In the left menu, open **Audience** and click **Publish app**, then confirm. This keeps the connection from expiring every seven days.
6. In the left menu, open **Clients**, click **Create client**, choose application type **Desktop app**, name it `Oso`, and click **Create**. Click **Download JSON** and save the file somewhere you can find it.
7. In the Oso window, click **Connect Google Calendar** and pick the file. Or run `oso connect-calendar --client-file "<path to the downloaded file>"`.
8. A browser window opens. Sign in, and if Google says the app is not verified, click **Advanced**, then **Go to Oso**. Allow access.

To stop it, run `oso disconnect-calendar`; the calendar stays until you delete it. Without this step, urgent changes still appear in your briefing; they just don't reach your calendar.

### Canvas sign-in

The calendar feed only brings in due dates. Signing in to Canvas through Oso adds your grades, scores, missing work, instructor comments, course files, announcements, and the messages instructors send you in the Canvas inbox. More in [Canvas](features/canvas.md).

1. In the Oso window, click **Sign in to Canvas**, or run `oso connect-canvas`.
2. A small window opens with your school's Canvas sign-in page. Sign in as usual, including any two-step check; the window closes by itself once you're in.
3. Optional: to have Oso sign in again on its own when Canvas logs you out, give it your school username and password once (Actions tab, **Canvas username and password…**). They're kept in your computer's credential store, never in a file.

If your school allows Canvas access tokens, you can use one instead: in Canvas, open **Account**, **Settings**, **+ New Access Token**, then run `oso init --vault "<your vault path>" --canvas-url https://<yourschool>.instructure.com --canvas-token <the token>`.

### School email

Oso reads one Gmail account: the one your school email is forwarded to. If your school email isn't forwarded there yet, add a rule in your school email that forwards everything to that Gmail address. More in [School messages](features/school-messages.md).

1. In the Google Cloud project from [the Oso calendar](#the-oso-calendar), search for **Gmail API**, open it, and click **Enable**.
2. In the Oso window, click **Connect email**. Or run `oso connect-email`.
3. A browser window opens. Sign in with the Gmail account your school email is forwarded to. If Google says the app is not verified, click **Advanced**, then **Go to Oso**, and allow Oso to read your email and send email. It sends only your feedback about Oso, to the person who builds it.

### GroupMe

Optional.

1. Go to [dev.groupme.com](https://dev.groupme.com) and sign in with your GroupMe account.
2. Click **Access Token** at the top right and copy it.
3. In the Oso window, click **Connect GroupMe** and paste it. Or run `oso connect-groupme`.

### Google Tasks

Your task list, on your phone. More in [Tasks](features/tasks.md).

1. In the Google Cloud project from [the Oso calendar](#the-oso-calendar), search for **Google Tasks API**, open it, and click **Enable**.
2. In the Oso window, click **Connect Google Tasks…**. Or run `oso connect-tasks`.
3. Sign in with the same Google account and allow Oso to manage your tasks.

Oso makes a list named **Oso** in Google Tasks. Tasks with a due day also show in the Google Calendar app; install the free Google Tasks app to see the whole list.

---

## Install the Oso plugin

The plugin is the set of instructions that teach Claude how to use Oso.

**In Cowork:**

1. In the sidebar, open **Customize**, then **Plugins**.
2. Select **Add marketplace** and enter `loganbecket/oso`.
3. The Oso plugin appears. Click **Install**. Then, on the same Plugins page, open the Oso marketplace's menu and turn on **Sync automatically**, so the plugin keeps itself up to date.
4. Open the installed plugin and go to its **Connectors** tab. The **oso** connector is listed as "Runs in each session"; there is nothing to click. Do not use **Add custom connector**; that is only for connectors hosted on the internet. (On Linux, where Cowork runs in the browser, this connector cannot reach your computer; use Claude Code for anything that needs it.)

**In Claude Code:** a plugin installed in Cowork is saved to your Claude account, so Claude Code has it too. On Linux, start Claude Code (`claude` in the command window) and type:

```
/plugin marketplace add loganbecket/oso
/plugin install oso@oso
```

---

## Set up your courses

1. In Cowork, click **Projects** in the sidebar and create a project named `School`. When it asks for a folder, pick your vault folder. Start every study chat inside this project. (In Claude Code, start `claude` from inside the vault folder instead.)
2. Open the course syllabus in your browser and clip it with the Web Clipper. It lands in your vault's `Clippings` folder and waits there for course setup. A syllabus PDF dragged into `Clippings` works too.
3. In a chat in the School project, type `/create-course` followed by the course name, for example `/create-course Intro to Engineering`.
4. Claude reads the syllabus and shows you every date, exam, and grade weight it found, and the class times: every lecture, lab, and discussion, with the room. Canvas doesn't have class times, so if the syllabus doesn't either, Claude asks you; your registration schedule has them. Check everything, correct anything wrong, and confirm. Only then does it create the course folder, file the syllabus, save the dates, and put your classes on the Oso calendar.
5. Repeat for each course.

---

## Schedule the morning briefing

In Cowork, create a scheduled task that runs every day at the time you wake up, with the instruction *"Run the oso-briefing skill."* It reads your day from the vault through Google Drive, and the result appears in the Claude app on your phone. It runs in Claude's cloud, so it works even when your computer is off. More in [The morning briefing](features/morning-briefing.md).

---

## Claude in Chrome

Needed only for `/scrape-page`, which saves online textbook pages to a course's book.

1. Install the Claude extension from the Chrome Web Store ([claude.ai/chrome](https://claude.ai/chrome)) and sign in with your Claude account.
2. The first time you run `/scrape-page` on a textbook site, allow Claude to read that site when the extension asks.

## A shared Google Drive folder

If a professor shares a Drive folder of lecture files, find it in your Drive folder on the computer and run:

```
oso set-drive-folder MATH-101-001 "<path to that folder>"
```

using the course code Oso printed when you set the course up. Its files are copied into the course folder on every check.

---

## Your reMarkable tablet

Optional, and only if you take notes on a reMarkable. Most students don't need this: scanned or photographed paper notes work just as well (see [Notes and handwriting](features/notes-and-handwriting.md)). Oso pulls your handwritten notes straight off the tablet over the USB cable. No reMarkable account or subscription is needed, and only your coursework comes over.

**A folder on the tablet with the same name as a course folder in your vault belongs to that course.** For a course in `Courses/2026 Fall/Physics`, make a folder called `Physics` on the tablet and keep that class's notebooks in it, sub-folders included. Notebooks anywhere else on the tablet are never touched.

1. On the tablet, open **Settings**, then **Storage**, and turn on **USB web interface**.
2. Make one folder per course, named exactly as the course folder in your vault (capital letters do not matter). To keep them together, put them all inside one folder such as `School` and run `oso set-remarkable-folder School` once.
3. Plug the tablet into your computer with its USB cable. The first time can take a minute. On Windows, if asked about a new network, choose **Private**.
4. The next time Oso syncs (within 15 minutes, or run `oso sync`), it copies any notebook you changed. Leave it plugged in for a few minutes.

If the computer doesn't see the tablet, make sure the tablet's software is up to date (Settings, General, Software). What happens to the pages next is in [Notes and handwriting](features/notes-and-handwriting.md).
