# Offsite backup to the home NAS: phased plan

Temporary planning document. Delete it when the last phase ships. This is a feature release: it ships as **v0.3.0**, after the Canvas release (v0.2.0).

## Goal

Everything Oso collects lives on one laptop: the vault (his notes, handwriting, clippings, mirrored course files, study guides, the learner profile) and the database (deadlines, grades, Canvas records, practice results). Google Drive syncs the vault, but syncing is not a backup: a deletion or a damaged file syncs too, and the database is not in Drive at all. A lost, stolen, or failed laptop mid-semester would take months of work with it.

This plan has Oso copy all of it every night to his home folder on the family Synology NAS, reached over Tailscale, and keep enough history that a file deleted or damaged weeks ago can still be recovered. A new laptop can be brought back to where the old one was with one command.

## Principles

- **Oso copies, the NAS keeps history.** Oso keeps an up-to-date copy on the NAS; the NAS's own snapshots keep the dated history. Each side does what it is good at, and nothing Oso does on the laptop can erase the NAS's history.
- **No connecting step.** Tailscale keeps the NAS reachable whenever the laptop is online. Oso never starts, stops, or configures a VPN. If he uses the home VPN instead, the backup simply runs whenever it happens to be connected.
- **No password stored by Oso.** The NAS sign-in is remembered by the operating system when he first opens the folder. Oso is given only the folder's location.
- **Quiet when it works, plain when it doesn't.** A night the NAS is unreachable is skipped without fuss. Several missed nights in a row become one line in the briefing.
- **Nothing sensitive leaves in a form Oso controls poorly.** Credentials (Canvas session, calendar, feed address) are never backed up; he signs in again after a restore. The search index is not backed up either; it is rebuilt from the vault.
- **Read-only toward the NAS except his backup folder.** Oso writes only inside the backup folder it was given.

## Phase 0: The NAS side (Logan, one evening)

A setup, not a build.

- Install Tailscale on the NAS (Synology Package Center) and on his laptop; sign in to the same account, or share only the NAS with his account. Turn on two-step sign-in for the Tailscale account. Leave the "reach the whole home network" and "send all traffic home" settings off.
- Confirm his NAS account can reach only his own home folder.
- Create a `Oso Backup` folder inside his home folder.
- Turn on scheduled snapshots for the shared folder that holds the home folders (Synology Snapshot Replication): nightly, keep 14 daily, 8 weekly, 12 monthly. Snapshots set read-only to his account.
- From the laptop, open the folder once in File Explorer (or Finder) and tick "remember my credentials."

**Done when:** with Tailscale on and the home VPN off, he can open `Oso Backup` from campus.

## Phase 1: The nightly backup

- **Backup folder** setting in `oso settings` (and `oso backup --set-folder`), checked on save: Oso writes and removes a small test file, and says plainly if it can't.
- `oso backup` runs one now, with a short plain summary when done ("Backed up 42 changed files and your database to the NAS").
- Nightly, as part of the regular scheduled check: the first check after 2 a.m. (or the first after waking, if the laptop slept through) runs the backup once for that day.
- What is copied:
  - the whole vault, copying only files that changed since last time
  - a safe copy of the database taken while Oso is running (not a raw file copy that could catch it mid-write), plus a dated copy of the database kept for 30 days, since it is small
  - Oso's settings file (no credentials)
- Files deleted from the vault are moved to a `Removed/<date>` folder in the backup rather than deleted, and cleared after 30 days. Together with the NAS snapshots, this covers mistakes noticed late.
- If the folder can't be reached, the night is skipped and retried at the next check; no error unless it keeps happening (Phase 2).
- A backup that is interrupted (lid closed, network dropped) resumes at the next check instead of starting over.

**Done when**
- Tests cover changed-files-only copying, the safe database copy, removed files being kept and later cleared, an unreachable folder being skipped quietly, and an interrupted backup resuming.
- A real run on his laptop fills `Oso Backup` on the NAS.

## Phase 2: Telling him how it's going

- `oso doctor` and `Dashboard.md` show the last successful backup and its size.
- After 3 days without a successful backup, `Today.md` (and so the morning briefing) carries one line: "Your notes haven't been backed up to the NAS since Friday. Turn on Tailscale and Oso will catch up." Gone at the next successful backup.
- The health check skill can explain the common causes in plain words: Tailscale off, NAS sign-in forgotten, folder full.

**Done when**
- Tests cover the line appearing at 3 days and clearing after a backup.

## Phase 3: Restoring

- `oso restore` on a fresh install: points at the backup folder, copies the vault and the database back, then reminds him to reconnect Canvas, Google, and the calendar. The next check rebuilds the search index and catches up.
- `oso restore --date <day>` restores the database from one of the dated copies.
- Single lost notes need no command: he opens the backup folder (or a NAS snapshot) and copies the file back.
- Restore never overwrites a vault that already has notes in it without asking first.

**Done when**
- Tests cover a full restore into an empty install and refusing to overwrite a non-empty vault without confirmation.
- A real restore into a test folder on another computer matches the laptop.

## Phase 4: Wrap-up

- README: setting up Tailscale and the NAS folder, what is and isn't backed up, how to restore.
- `oso fresh-start` leaves the backup folder and its contents alone and says so.
- Release as v0.3.0. Delete this document.

## Decisions

Defaults below; easy to revisit.

1. **History on the NAS side, not in Oso.** Recommended: NAS snapshots do the dated history. The alternative, Oso keeping dated full copies itself, would use far more space and time over the connection.
2. **Encryption of the backup.** Default: none beyond what Tailscale and the NAS already provide, since it is the family's own NAS. Revisit if the backup ever goes to a cloud service.
3. **Backup time.** Default: first check after 2 a.m. daily.
4. **Missed-backup warning.** Default: after 3 days.
