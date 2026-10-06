# Morning briefing

Turn the facts in `Today.md` into a short briefing the student can read on a phone in under a minute.

## Where the facts are

- Call the `today` tool. If it is unavailable (for example in a cloud scheduled task), read `Today.md` at the root of the vault through Google Drive.
- Do not look anywhere else for deadlines. `Today.md` is the only source; if it is missing or more than a day old, say so and stop.

## Shape

1. One line: the date and the single most important thing today.
2. **Due today**, each item as one line: course, item, time or day, weight if known. Overdue items first, marked plainly.
3. **Readiness**, right after Due today, if `Today.md` has that section: each exam line as written, then one sentence on the single most useful thing to do about it. Offer a study plan working back from the exam and a practice test on the weak topics. **Missing work** from Canvas goes here too, plainly.
4. **Due this week**, in the same one-line form.
5. **Changes** since yesterday, if any, including new grades and comments under "From Canvas". Urgent ones (a moved due date, a rescheduled exam) go first.
6. **Exams**: a countdown for each upcoming exam.
7. **Focus**: one or two sentences on what to work on today and why, judged from weight, proximity, and readiness. Do not pad.
8. Any **connection** problem from `Today.md`, in the same plain words it uses; a Canvas sign-in request goes first.

## Canvas topics (when Today.md says assignments are not yet matched to topics)

Before writing the briefing, for each course with unmatched assignments: call `canvas_info` with `untagged`, decide which of the course's topics each assignment covers from its name and group (a homework titled "HW 4: Newton's laws" covers "Newton's Laws"; an assignment that covers no listed topic, like a syllabus quiz, gets none), and save with `tag_assignments`. Leave an assignment out if you can't tell; it will come up again. Don't mention this in the briefing.

## Rules

- Short by default. Skip empty sections. Expand only if asked.
- Never invent an item, a date, or a weight that is not in `Today.md`.
- Link each item to its Canvas page when a link is present.
- For the Sunday review, add what was completed last week and the total load for the coming week, then the practice-habits note below.

## Practice habits (Sunday review only)

1. Call `practice_habits`. If `enough_data` is false, skip this part entirely.
2. Write three to five plain sentences about how he practices, using only what the numbers show: how far ahead of exams he started practice quizzes, whether he retests topics he missed and whether the retests go better, whether scores in each course are rising or fading, and whether his practice goes to the courses whose grades and upcoming work need it. Name the number behind each claim ("first practice quiz for Exam 1 came 1 day before it"). Describe what he did, never what kind of person he is; no "procrastinates", "lazy", or "great job". If a number does not support a sentence, leave the sentence out.
3. Call `save_habits_summary` with those sentences, and put the single most useful one in the briefing.
