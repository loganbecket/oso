---
name: oso-doctor
description: Look after Oso itself. Use when the student says open my settings, open Oso, Oso status, is Oso OK, update Oso, sync now, back up now, or when the briefing is missing, deadlines look stale, or a connection shows as failing.
---

# Looking after Oso

Everything here works from Cowork through the Oso tools. Answer in plain sentences; never show commands, paths, or error text unless the student asks.

**"Open my settings", "open Oso", "show me Oso's settings":** call `open_settings`. The Oso window opens on his laptop (or comes to the front if it is already open), on a status panel with a button beside anything that needs doing. Say so in one line. If the tool is unavailable (he is on his phone, or Oso is not running), say the window only opens on the laptop and give the status in chat instead.

**"Oso status", "is Oso OK?":** call `oso_status` and show a short status card: one line per item that needs attention first (what is wrong, and what fixes it), then one line saying everything else is fine. Leave out the technical detail. Offer to fix what you can: `run_health_check` with fix, `sync_now`, `update_oso`, `backup_now`, or `open_settings` for things only he can do (signing in to Canvas, connecting Google Calendar).

**Something looks broken** (briefing missing, deadlines stale, a source failing):
1. Call `run_health_check` with `fix` true and read every line.
2. For what is still wrong: no recent check, call `sync_now`; a newer version is out, offer to update and, when he says yes, call `update_oso` with `confirmed` true; the Canvas sign-in lapsed, call `open_settings` and tell him to press Sign in to Canvas; the calendar feed is rejected, he needs to copy a fresh Calendar Feed address from Canvas (Calendar, then Calendar Feed) into the Settings tab. Do not guess at addresses or tokens.
3. Explain anything still wrong in one or two plain sentences.

**"Update Oso":** call `update_oso` with `confirmed` true (he asked in this chat). On Windows a window opens and installs the update, and this chat's connection to Oso restarts; tell him to restart the Claude app when the window closes.

**If the Oso tools are not available at all**, Oso itself is not running in the Claude app. In Claude Code on the laptop, run `oso doctor --fix` in the terminal and follow it; otherwise tell him to run that in PowerShell.

Starting over (fresh start) is never done from chat. If he asks, tell him it is the PowerShell command `oso fresh-start`, which asks him to confirm.
