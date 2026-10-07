# Managing Oso from Claude: phased plan

Temporary planning document. Delete it when the last phase ships. This is a feature release: it ships as **v0.6.0**.

## Goal

Once Oso is set up, the student lives in Cowork and forgets Oso exists, which is mostly good. The risk is that looking after it (updates, health checks, a lapsed sign-in, backups) still means remembering PowerShell commands, so it gets neglected.

This plan makes Cowork the one place Oso is managed, with the existing settings window as its visual panel:

- He says "open my settings" in Cowork and the Oso window opens on his laptop.
- The window opens on a status panel showing everything that matters, with a button beside anything that needs doing.
- Everything that today needs PowerShell can be done from that window, or by asking Claude.
- A Start menu shortcut opens the same window without Cowork.

No new application, no second dashboard. Problems still come to him through the morning briefing; this is where he goes to see the whole picture or act on it.

## Principles

- **One place.** Cowork is how he manages Oso. The window is what Cowork opens when a picture or a button is better than a chat reply. Nothing new to remember.
- **Plain status, one click to fix.** Each line says what is fine or what is wrong in a sentence, and anything wrong has the button that fixes it beside it.
- **Same actions everywhere.** A button in the window and a request in chat run the same code, and report the same plain sentence.
- **Laptop only.** The window opens on the laptop where Oso runs. From the phone, Claude says so and offers the chat version of the status instead.
- **Dangerous things stay deliberate.** Fresh start stays a PowerShell command with its typed confirmation; it is not a button.

## Phase 1: "Open my settings" from Cowork

- An Oso tool that opens the settings window on his laptop, the same way the quiz window opens. Claude calls it for "open my settings", "open Oso", "show me Oso's settings", and the like.
- If the window is already open, it is brought to the front instead of opening a second one.
- If it can't open (phone, or Oso not running), Claude says so in one line and offers the status in chat (Phase 3).

**Done when**
- Tests cover the launch, and a second request not opening a second window.

## Phase 2: A status panel at the top of the window

The window opens on **Status**, with the existing settings below (or on a second tab). Each line is a plain sentence with a colored mark (fine, needs attention, broken) and, where something needs doing, a button:

| Line | Button when it needs attention |
| --- | --- |
| Oso version and update channel; whether a newer version is out | Update |
| Last check, and whether the automatic 15-minute check is scheduled | Fix |
| Folder watcher running | Fix |
| Canvas calendar feed: last successful read | Fix (opens the feed setting) |
| Canvas sign-in: connected, needs sign-in, or not set up | Sign in to Canvas |
| Google Calendar: connected or not | Connect |
| reMarkable: last pull | (none; plug it in) |
| Backup: last successful backup, or not set up | Back up now |
| Search: how much of the vault is indexed | (none) |
| Books: still being read, or done | (none) |
| Pages waiting for Claude to read | (none) |
| Command updates waiting for his decision | (none; ask Claude) |
| Followed instructor websites that can't be read | (none) |

- A **Refresh** button re-reads everything; the panel also refreshes after any button finishes.
- The same facts as `oso doctor`, computed by the same code, so the two never disagree.

**Done when**
- Tests cover each line in its fine and needs-attention states (from stored facts, without a live network), and each button calling the right action.

## Phase 3: Every PowerShell-only action, in the window and in chat

**In the window**, alongside the status buttons: Run the health check (with fixes), Sync now, Update Oso, Transcribe now, Back up now, Connect / Disconnect Canvas, Connect Google Calendar, Books (progress, read again), Instructor websites (list, check now, add, remove). Results show in plain sentences in the window. Fresh start is not here.

**In chat**, Oso tools so Claude can do the same when asked:
- `oso_status`: the status panel's facts, which Claude shows as a short status card ("Oso status", "is Oso OK?")
- `run_health_check` (with or without fixes), `sync_now`, `update_oso` (the visible update window opens on the laptop, as today)

The health-check command's instructions change from "run it in a terminal" to these tools, so it works in Cowork.

**Done when**
- Tests cover each tool returning the same result as its button, and the status card having no technical detail in it.

## Phase 4: A Start menu shortcut

- The installer and every update create an **Oso** shortcut in the Start menu (Windows), Applications (macOS), and the app menu (Linux) that opens the settings window, with no command window behind it.
- He can pin it to the taskbar himself (Windows doesn't let programs pin themselves).

**Done when**
- Tests cover creating the shortcut; a real update on the Windows test machine creates it.

## Phase 5: Wrap-up

- README: "open my settings" and "Oso status" in Cowork as the way to look after Oso; the shortcut; PowerShell commands kept as a reference at the end.
- Release v0.6.0. Delete this document.

## Decisions

Defaults below; easy to revisit.

1. **Status first, settings second**, as two tabs in the same window, so the first thing he sees is whether Oso is healthy.
2. **Fresh start stays a PowerShell command**, never a button or a chat request.
3. **No separate dashboard in Obsidian**, to keep to one place.
