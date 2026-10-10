# When something's wrong

Start by asking Claude *"is Oso OK?"*, or say *"open my settings"* and look at the status panel in the Oso window. It checks every part of Oso, fixes what it can, and puts a button beside anything you need to do. In a command window, `oso doctor --fix` does the same.

| What you see | What to do |
| --- | --- |
| The installer says setup closed before a vault was chosen | The setup window was closed on its first step. Run the installer again and choose your vault; nothing else is lost. |
| Urgent changes or classes aren't reaching my calendar | Run `oso doctor`. If it says Google Calendar is not connected, [connect the Oso calendar](install.md#the-oso-calendar). If the connection expired, check the Google project is published (step 5 there) and connect again. |
| My tasks aren't on my phone | Check Google Tasks is connected (status panel). Tasks with a due day show in Google Calendar; for the whole list, install the free Google Tasks app and open the list named **Oso**. |
| The briefing did not arrive | Open the Claude app and check the scheduled task ran. Then check `Today.md` in your vault is from today; if not, run `oso doctor`. |
| The briefing says Oso doesn't know when a course meets | Tell Claude the class times (days, times, room, last day of classes); your registration schedule has them. |
| `Today.md` says Canvas has not synced in many hours, or deadlines never change | Your computer may have been off. Turn it on and wait a few minutes, or run `oso sync`. If it keeps happening, run `oso doctor --fix`; it recreates the automatic check if it is missing. |
| Canvas says the login was rejected or the address no longer works | Get a fresh [calendar feed address](install.md#get-your-canvas-calendar-feed) and run `oso init` again with it. |
| Canvas needs you to sign in again | Click the notification, or press **Sign in to Canvas** in the Oso window. |
| `oso` is not recognized as a command | Close the command window and open a new one. If it still fails, run `uv tool update-shell`, then open another new window. |
| Claude says it cannot reach Oso's tools | Run `oso doctor`. If it says `oso-mcp` is missing, [run the installer](install.md#run-the-installer) again. Then restart the Claude app. |
| Every `oso` command prints `No module named 'oso'`, or an install says `Access is denied` | An update was interrupted while Oso was running. Quit the Claude app and run the installer again; your settings and deadlines are kept. |
| `oso install-task` says `Access is denied` | You have a version older than v0.1.1. Run the installer again. |
| A handwritten page came out wrong | The original page image is linked at the bottom of the note. Fix the text in Obsidian; Oso never overwrites your edits. |
| My reMarkable tablet doesn't sync (if you use one) | Check **USB web interface** is on, the cable is in, and the tablet software is current. Check the notebook is inside a folder named after the course. Run `oso sync` while it is plugged in. |
| I want to start over | Quit the Claude app and run `oso fresh-start`. It deletes everything in the vault (except Obsidian's settings and your textbooks) and everything Oso has recorded, including your rules, with no backup. It keeps your settings and connections and pulls your Canvas deadlines back in. Then set up each course again with `/create-course`. |
