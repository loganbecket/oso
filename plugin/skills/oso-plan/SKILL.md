---
name: oso-plan
description: Build a study plan working back from exam and deadline dates and put the study blocks on the student's calendar. Use when asked to plan the week, schedule studying, or prepare for an exam over time.
---

# Study plan

## Gather

1. `list_deadlines` for the next 21 days (longer if an exam is further out). Note weights and kinds.
2. Ask the student two things if not already known this session: which hours are usually free for studying (for example weekday evenings 7 to 10, Saturday afternoons), and whether to put the blocks on the calendar or just show the plan.
3. For an exam, get its scope from `Course.md` and any study guide in `Courses/<folder>/Exams/`. Check `Courses/<folder>/Notes/Practice log.md` for weak topics.

## Plan

- Work backward from each due date. Heavier weight and nearer dates get more and earlier time. Exams get spaced sessions over several days, not one long block, and the last session before an exam is review, not new material.
- Blocks of 60 to 120 minutes with a stated goal each ("Chain rule problems 1 to 10 from HW 4", "Review study guide topics 1 to 3"). Never more than the free hours the student gave.
- Leave the day before a deadline with a finishing block, not a starting one.

## Deliver

- Show the plan as a day-by-day list.
- If the student said yes to the calendar, create each block on the **Oso** Google Calendar through the Calendar connector with the goal as the title and a 15-minute reminder.
- Save the plan to `Courses/<folder>/Exams/<exam or week> plan.md` (or `Inbox/Study plan <date>.md` for a general week), front matter `type: study-plan`.

Only the Oso calendar is ever written to.
