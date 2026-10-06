# Urgent alerts

Oso's service normally delivers urgent changes to the Oso calendar by itself. Use this skill when the student asks what changed, or when the service's calendar connection is not set up (`Today.md` or `oso doctor` will say so) and they want the alerts on the calendar anyway.

## Steps

1. Read `Oso/Alerts.md` in the student's vault through the Google Drive connector. If it is missing or has no lines, say "No urgent changes" and stop. (If the `pending_alerts` tool happens to be available, you may use it instead; it returns the same information.)
2. Consider only lines noticed in the last 7 days. Each line is: `when noticed | what changed | due <date> | <link> (flags)`.
   - Skip lines marked `(muted)`.
   - Skip lines marked `(quiet until <time>)` if that time is still in the future.
3. The event title is `Oso: <what changed>` with the `**` bold markers removed (for example `Oso: Calculus I: Homework 1 moved from Wed Oct 07 to Fri Oct 09`); the service uses exactly the same title. For each remaining line, look in the student's **Oso** Google Calendar for an event with that title. If one exists, the alert was already delivered; skip it.
4. Otherwise create the event on the **Oso** calendar with that title, at the item's due date and time (if the due date is `no date`, today at 6 pm), with reminders 1 day before and 2 hours before, and the link in the description. If the `mark_alert_reported` tool is available, call it with the alert number from the line's trailing comment.
5. Reply with one line per event created, or "Nothing new" if none.

## Rules

- Never write to any calendar other than the Oso calendar.
- Never create an event whose title already exists on the Oso calendar; the title check is what prevents duplicates.
- Do not edit `Alerts.md`.
