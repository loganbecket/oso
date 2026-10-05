---
name: oso-alerts
description: Deliver urgent coursework changes (moved due dates, rescheduled exams, new items due soon) to the student's Google Calendar. Run as a scheduled task every few hours, or when asked to check for alerts.
---

# Deliver urgent alerts

1. Call `pending_alerts`. If empty, say "No urgent changes" and stop.
2. For each alert whose `deliver_after` is null or already past:
   - Create an event on the student's **Oso** calendar through the Google Calendar connector: title `Oso: <message>`, at the item's `due_at` if it has one (otherwise today at 6 pm), with a reminder 1 day before and another 2 hours before. Put the item's link in the description.
   - Call `mark_alert_reported` with the `alert_id`.
3. Alerts with a `deliver_after` in the future are inside quiet hours: leave them for the next run and say so.
4. Reply with one line per alert delivered.

Never create duplicate events: if `mark_alert_reported` was already called for an alert, it will not appear again. Never write to any calendar other than the Oso calendar.
