# Oso

Oso is a study assistant for college students. It keeps track of everything that is due across all your classes, sends you a short briefing on your phone every morning, warns you when a due date moves, and helps you study from your own notes: it explains topics, builds study guides and practice tests, and checks your work, always pointing back to the note it got the answer from.

It is built from three things you already have or can get: **Obsidian** (a free notes app) holds everything you read and write; **Claude** (on a Pro subscription) supplies the intelligence; and a small program on your laptop, the **Oso service**, does the plumbing: pulling Canvas and your reMarkable tablet, keeping the list of deadlines, and noticing changes. Nothing runs on a server anywhere. Nobody else can see your notes. You install it once and it is yours.

Everything below is written for someone who has never opened a terminal. It takes about an hour, most of it installing and signing in to apps. Do the sections in order.

---

## Part 1: Accounts and apps

### 1.1 Google account

You need a Google account (a Gmail address). Oso uses Google Drive to carry your notes to your phone and to Claude, and Google Calendar for alerts. If your school gives you a Google account, that works too.

Turn on two-step verification for the account if you have not: go to [myaccount.google.com/security](https://myaccount.google.com/security) and follow "2-Step Verification". Your notes will live in this account, so protect it.

### 1.2 Claude Pro

1. Go to [claude.ai](https://claude.ai) and sign in or create an account.
2. Upgrade to the **Pro** plan (about $20 a month). Oso needs Pro for Cowork, scheduled tasks, and Claude Code.
3. In Settings, find the **privacy** or **data** section and decide whether Claude may use your conversations to improve its models. Oso works either way; this is your choice, but make it deliberately, because your coursework will pass through Claude.

### 1.3 Claude desktop app and phone app

1. Download the Claude desktop app for Windows from [claude.ai/download](https://claude.ai/download) and install it. Sign in.
2. In the app, find **Cowork** in the sidebar. Cowork is the mode where Claude can work with folders on your computer. Open it once so it is set up.
3. On your phone, install the Claude app from the App Store or Google Play and sign in with the same account. The morning briefing arrives here.

### 1.4 Google Drive for Desktop

1. Download Google Drive for Desktop from [google.com/drive/download](https://www.google.com/drive/download/) and install it. Sign in with your Google account.
2. When it asks how to sync, choose **Stream files** or **Mirror files**; either works. After it finishes, you will have a folder on your computer, usually `G:\My Drive` or `C:\Users\<you>\My Drive`. Everything in it is copied to Google automatically.

### 1.5 Obsidian

1. Download Obsidian from [obsidian.md](https://obsidian.md) and install it. It is free.
2. Open Obsidian. Choose **Create new vault**. Name it `Vault` (or anything you like) and, for the location, pick a folder **inside your Google Drive folder** from step 1.4, for example `My Drive\Vault`. This matters: it is how your phone and Claude see your notes.
3. Install the Obsidian Web Clipper in your browser from [obsidian.md/clipper](https://obsidian.md/clipper). It is the button you press to save a web page or paper into your notes. When it asks for a vault, pick the one you just made.
4. Optional, for flashcards: in Obsidian, open Settings, then **Community plugins**, turn them on, browse, search for **Spaced Repetition**, install it, and enable it.
5. Optional, on your phone: install the Obsidian app and open the same vault from Google Drive, or use Obsidian's own Sync service if you prefer.

### 1.6 Claude Code

Claude Code is Claude in a command window. You only use it for two things: installing Oso, and transcribing your handwritten notes. Install it by following the instructions at [claude.ai/code](https://claude.ai/code) for Windows. Sign in with the same Claude account.

### 1.7 Git and this repository

1. Install Git for Windows from [git-scm.com/download/win](https://git-scm.com/download/win). Accept the defaults.
2. Open **PowerShell** (press the Windows key, type `PowerShell`, press Enter) and run:

   ```
   git clone https://github.com/loganbecket/oso C:\Oso
   ```

   This copies Oso's files into a folder called `C:\Oso`.

---

## Part 2: Install the Oso service

### 2.1 Get your Canvas calendar feed

Canvas is your school's course website where assignments and grades are posted. Every Canvas account has a private calendar feed that Oso reads.

1. Sign in to Canvas in your browser.
2. Click **Calendar** in the left menu.
3. On the right side of the calendar page, click **Calendar Feed**.
4. A box appears with a long web address starting with `https://` and ending in `.ics`. Copy the whole thing. Treat it like a password: anyone with it can see your calendar.

### 2.2 Run the installer

In PowerShell, run (replace the vault path with yours from step 1.5):

```
powershell -ExecutionPolicy Bypass -File C:\Oso\install.ps1 -Vault "C:\Users\<you>\My Drive\Vault"
```

The installer:

- installs a small Python helper called `uv` if you do not have it
- installs the Oso service
- adds the starting folders to your vault
- asks you to paste the Canvas calendar feed address from step 2.1 (right-click to paste, then Enter)
- schedules Oso to check for changes every hour, even when the laptop is asleep
- runs a first sync and a health check

When it finishes it prints a short report. Lines starting with `ok` are fine. Anything marked `WARN` or `FAIL` says what to do in plain words.

If your time zone is not US Eastern, add `-Timezone "America/Chicago"` (or `America/Denver`, `America/Los_Angeles`) to the command.

### 2.3 Check it worked

Open your vault in Obsidian. There is now a file called `Today.md`. It lists what is due, what changed, and whether Canvas is connected. It is rewritten every hour; do not edit it.

If `Today.md` is missing or Canvas shows as not connected, run `oso doctor` in PowerShell and follow what it says.

---

## Part 3: Connect Claude to Oso

### 3.1 Connect Google to Claude

In the Claude desktop app, open **Settings**, then **Connectors**. Connect **Google Drive**, **Google Calendar**, and **Gmail**, signing in with your Google account each time. Drive is required; Calendar is needed for alerts and study blocks; Gmail is optional.

### 3.2 Create the Oso calendar

Go to [calendar.google.com](https://calendar.google.com). On the left, next to "Other calendars", click **+** and choose **Create new calendar**. Name it `Oso`. Oso only ever writes to this calendar, so you can turn it off or delete it any time without touching the rest of your calendar.

### 3.3 Install the Oso plugin

The plugin is the set of instructions that teach Claude how to use Oso.

**In Cowork (the Claude desktop app):**

1. In the sidebar, open **Customize**, then **Plugins**.
2. Select **Add marketplace** and enter `loganbecket/oso`.
3. The Oso plugin appears. Click **Install**.
4. Open the installed plugin and go to its **Connectors** tab. Connect the **oso** connector. This is what lets Claude read your deadlines and notes.

**In Claude Code:** open PowerShell and run:

```
claude plugin install C:\Oso\plugin
```

### 3.4 Set up your first course

1. Save each course's syllabus into your vault's `Inbox` folder (drag the PDF in through Obsidian, or save it there with your browser).
2. In Cowork, open your vault folder and say: *"Set up my Calculus course from the syllabus in Inbox."*
3. Claude reads the syllabus and shows you every date, exam, and grade weight it found. Check them, correct anything wrong, and confirm. Only then does it save anything.
4. Repeat for each course.

### 3.5 Schedule the morning briefing and alerts

In Cowork, create two scheduled tasks (the Cowork guide calls these tasks that Claude runs automatically):

- **Morning briefing**: every day at the time you wake up. Instruction: *"Run the oso-briefing skill."* It reads `Today.md` from your vault through Google Drive and the result appears in the Claude app on your phone.
- **Alerts**: every 3 hours. Instruction: *"Run the oso-alerts skill."* It puts moved due dates and rescheduled exams on your Oso calendar so your phone buzzes.

These run in Claude's cloud, so they work even when your laptop is closed.

---

## Part 4: Your reMarkable tablet

Oso pulls your handwritten notes straight off the tablet over the USB cable. No reMarkable account or subscription is needed, and only your coursework comes over.

The rule is simple: **a folder on the tablet with the same name as a course folder in your vault belongs to that course.** When you set up a course in Part 3, Oso created a folder for it in the vault under `Courses`, for example `Courses\Physics`. Make a folder called `Physics` on the tablet and keep that class's notebooks in it. Every notebook in that folder, including any sub-folders you make, is copied into `Courses\Physics\Handwriting` in your vault. Notebooks anywhere else on the tablet, like a journal or a to-do list, are never touched.

1. On the tablet, open **Settings**, then **Storage**, and turn on **USB web interface**.
2. On the tablet, make one folder per course, named exactly as the course folder in your vault (capital letters do not matter). If you would rather keep them together, put them all inside one folder such as `School` and run `oso set-remarkable-folder School` once in PowerShell.
3. Plug the tablet into your laptop with its USB cable. Windows adds it as a small network device; the first time can take a minute. If Windows asks about a new network, choose **Private**.
4. The next time Oso syncs (within the hour, or run `oso sync` in PowerShell), it copies any notebook you changed. Leave it plugged in for a few minutes; charging it at your desk is enough.
5. To turn the pages into notes you can search, open Claude Code in your vault folder (`claude` in PowerShell from that folder) and say: *"Transcribe my handwritten notes."* Claude reads each page, writes it out with the equations, files it in the right course automatically, and tells you about any page it could not read well. Those also show up in your morning briefing.

**If Windows does not see the tablet:** make sure the tablet's software is up to date (Settings, General, Software). Older tablet versions used a connection type that recent Windows releases dropped.

---

## Part 5: Everyday use

- **Every morning** the briefing is in the Claude app on your phone: due today, due this week, what changed, days until each exam, and what to focus on.
- **Reading online**: click the Web Clipper to save a page or paper into your vault. Pick the course folder when it asks.
- **Course files**: anything your professor posts to Canvas (with a Canvas token, see below) or to a shared Google Drive folder is copied into the course folder and turned into readable text.
- **Studying**: open Cowork on your vault and ask. Examples:
  - "Explain the chain rule from my notes."
  - "Make a study guide for the physics midterm."
  - "Quiz me on chapter 3."
  - "Here's my attempt at problem 4, where did I go wrong?" (attach a photo)
  - "What do I need on the final to get an A in chemistry?"
  - "Plan my studying for next week and put it on my calendar."
  - "Make flashcards for the vocabulary in lecture 5."
- **Grades**: Oso tracks them if your school allows a Canvas token (below). Otherwise tell Claude a grade and it records it.
- **Something looks wrong**: in Claude Code say *"Run the Oso doctor"*, or in PowerShell run `oso doctor --fix`.

### Optional: a Canvas token

If your school allows it, a token lets Oso read grades, announcements, and course files from Canvas, not just dates. In Canvas, open **Account**, then **Settings**, scroll to **Approved Integrations**, and click **+ New Access Token**. Name it `Oso`, leave the expiry blank, and copy the token. Then in PowerShell:

```
oso init --vault "C:\Users\<you>\My Drive\Vault" --canvas-url https://<yourschool>.instructure.com --canvas-token <paste the token>
```

If the **+ New Access Token** button is missing, your school has turned tokens off. The calendar feed still gives Oso every deadline.

### Optional: a shared Google Drive folder

If a professor shares a Drive folder of lecture files, find it in your Drive folder on the computer and run:

```
oso set-drive-folder MATH-101-001 "C:\Users\<you>\My Drive\Shared with me\MATH 101 Lectures"
```

(use the course code Oso printed when you set the course up).

---

## Part 6: Problems

| What you see | What to do |
| --- | --- |
| The briefing did not arrive | Open the Claude app and check the scheduled task ran. Then check `Today.md` in your vault is from today; if not, run `oso doctor`. |
| `Today.md` says Canvas has not synced in many hours | Your laptop may have been off. Open it and wait an hour, or run `oso sync`. If it keeps happening, run `oso install-task` again. |
| Canvas says the login was rejected or the address no longer works | Get a fresh calendar feed address (step 2.1) and run `oso init` again with it. |
| Claude says it cannot reach Oso's tools | Run `oso doctor`. If it says `oso-mcp` is missing, run the installer again. Then restart the Claude app. |
| A handwritten page came out wrong | The original page image is linked at the bottom of the note. Fix the text in Obsidian; Oso never overwrites your edits. |
| The tablet does not sync | Check **USB web interface** is on, the cable is in, and the tablet software is current. Check the notebook is inside a folder named after the course. Run `oso sync` while it is plugged in. |
| I want to start over | Delete the vault folder and the Oso data folder (`oso doctor` prints where it is). Run the installer again. |

## Commands

```
oso sync                  pull every source and rewrite Today.md and Dashboard.md
oso doctor [--fix]        check the installation and explain anything wrong
oso health                when each source last synced
oso add-course            register a course by hand
oso set-drive-folder      mirror a shared Google Drive folder into a course
oso set-remarkable-folder the tablet folder that holds the course folders
oso install-task          schedule the hourly sync
```

## For developers

The design is in [docs/spec.md](docs/spec.md) and the build plan in [docs/plan.md](docs/plan.md). The service is in `service/`, the Claude plugin in `plugin/`, tests in `tests/`. Run tests with `uv run pytest`.

## License

MIT. See [LICENSE](LICENSE).
