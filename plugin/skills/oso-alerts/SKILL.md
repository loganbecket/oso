---
name: oso-alerts
description: Deliver urgent coursework changes (moved due dates, rescheduled exams, new items due soon) to the student's Google Calendar. Run as a scheduled task every few hours, or when asked to check for alerts.
---

# Deliver urgent alerts

This runs in Claude's cloud as a scheduled task, where Oso's local tools are not available, so it works from a file and the calendar alone. The same steps work when run locally.

## Steps

1. Read `Inbox/Alerts.md` at the root of the student's vault through the Google Drive connector. If it is missing or has no lines, say "No urgent changes" and stop. (If the `pending_alerts` tool happens to be available, you may use it instead; it returns the same information.)
2. Consider only lines noticed in the last 7 days. Each line is: `when noticed | what changed | due <date> | <link> (flags)`.
   - Skip lines marked `(muted)`.
   - Skip lines marked `(quiet until <time>)` if that time is still in the future.
3. For each remaining line, look in the student's **Oso** Google Calendar for an event titled exactly `Oso: <what changed>`. If one exists, the alert was already delivered; skip it.
4. Otherwise create the event on the **Oso** calendar: title `Oso: <what changed>`, at the item's due date and time (if the due date is `no date`, today at 6 pm), with reminders 1 day before and 2 hours before, and the link in the description. If the `mark_alert_reported` tool is available, call it with the alert number from the line's trailing comment.
5. Reply with one line per event created, or "Nothing new" if none.

## Rules

- Never write to any calendar other than the Oso calendar.
- Never create an event whose title already exists on the Oso calendar; the title check is what prevents duplicates.
- Do not edit `Alerts.md`.
