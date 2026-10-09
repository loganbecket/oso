# Looking after Oso

Oso mostly looks after itself. When something needs you, it says so in plain words, and you can fix it from the Claude app or the Oso window.

## What it's for

Oso runs quietly in the background on your computer. This is everything around keeping it healthy: checking how it's doing, updating it, changing settings, backing up, and starting over if you ever need to.

## The Oso window

Open it any of these ways:

- Say "open my settings" in the Claude app.
- On Windows, press **Ctrl+Alt+O** from anywhere.
- Open **Oso** from your Start menu (Applications on a Mac).
- Run `oso settings` in your command window.

It opens on a **status panel** that says what's fine and what needs attention. Anything that needs doing has a button beside it: Update Oso, Sign in to Canvas, Sync now, Connect Google Calendar, Connect email, Connect Google Tasks, Back up now. The **[Grades](grades.md)** tab lists your grade in each class, the **Actions** tab has every action in one place, and the **Settings** tab holds your settings.

The window only opens on your laptop. On your phone, ask Claude instead.

## Asking Claude

- "Is Oso OK?" or "Oso status": a short status card, problems first.
- "Sync now": check every source right away.
- "Update Oso"
- "Back up now"
- "Open my settings"

If something looks broken (the briefing is missing, deadlines look stale), Claude runs a health check, fixes what it can, and tells you plainly what's left. In a command window, `oso doctor --fix` does the same.

## Updates

When a new version is out, your briefing says so. Say "update Oso," click **Update Oso** in the window, or run `oso update`. On Windows, a window shows the update and closes by itself; then restart the Claude app. Your notes, deadlines, and settings are kept.

- **Channels.** By default you get **stable**: only versions marked as releases. To get every change as soon as it's published, set **Updates** to **latest** on the Settings tab.
- **Going back.** If a new version causes trouble, `oso update --version v0.14.0` (or any earlier release) installs that one.
- **The plugin.** Oso has a second piece inside the Claude app, the plugin. With **Sync automatically** turned on for the Oso plugin, it updates itself. Otherwise, click **Check for updates** on the Oso plugin under Customize, Plugins.

## Settings

The Settings tab is where you change the vault folder, time zone, how often Oso checks (15 minutes by default), what counts as urgent, quiet hours, muted courses, email senders and GroupMe groups to ignore, daily limits on how much Claude reads, the models used, the tablet folder, the backup folder, and the Canvas feed. **Save and check** applies changes and runs a health check.

## Backups

Set a backup folder on the Settings tab (a network drive, an external drive, any folder). Every night Oso copies your vault and its records there. Only changed files are copied, and files you delete are kept for 30 days. Say "back up now" to run one right away. Your briefing tells you if backups have stopped for several days.

To bring everything back on a new computer, install Oso and run `oso restore --from <backup folder>`.

## When a semester ends

Tell Claude "mark Calculus II finished." Your briefing suggests this once a course has had nothing due for two weeks. A finished course leaves the briefing, deadlines, and everyday searches, but its notes stay where they are and can still be searched by naming the course. "Make Calculus II current again" undoes it.

## Starting over

Quit the Claude app and run `oso fresh-start` in your command window; it asks you to confirm. It deletes everything in your vault except Obsidian's settings and your textbooks, plus everything Oso has recorded, with no backup. Your settings and connections are kept, and your Canvas deadlines come back on the next check. Then set up each course again. Fresh start is never done from a chat.

## Good to know

- Your passwords and sign-ins live in your computer's credential store, never in a file.
- Three settings pick which Claude model does background work: one for reading handwriting, one for study guides and practice tests, and one for acting on your rules and reading school email and GroupMe. Lowering one never changes the others.
- Problems Oso can't fix itself are covered in [Troubleshooting](../troubleshooting.md). Every command is in the [command reference](../commands.md).
