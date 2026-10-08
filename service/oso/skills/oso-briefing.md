# Morning briefing

Turn the facts in `Today.md` into a short briefing the student can read on a phone in under a minute.

## Where the facts are

- Call the `today` tool. If it is unavailable (for example in a cloud scheduled task), read `Today.md` at the root of the vault through Google Drive.
- Do not look anywhere else for deadlines. `Today.md` is the only source; if it is missing or more than a day old, say so and stop.

## Shape

1. One line: the date and the single most important thing today. If anything changes today's classes, that is it.
2. **Class today**, first, if anything in `Today.md` affects a class meeting today or tomorrow morning: a class canceled or moved (time or room), something to bring (a calculator, a lab coat, a printed reading), and anything to do before class (a reading, a pre-lab, a form). Take these from Heads up, Changes, From Canvas, and From instructors' websites, one line each, with the class time. Say them here and nowhere else in the briefing. Skip the section when there is nothing.
3. **Due today**, each item as one line: course, item, time or day, weight if known. Overdue items first, marked plainly.
4. **Readiness**, right after Due today, if `Today.md` has that section: each exam line as written, then one sentence on the single most useful thing to do about it. Offer a study plan working back from the exam and a practice test on the weak topics. **Missing work** from Canvas goes here too, plainly.
5. **Today's schedule**, if `Today.md` has it: classes, meetings, and events in time order, one line each. Then **Heads up**, plainly: something moved or canceled, an event the evening before an exam, two things at once, something he has to do soon.
6. **Due this week**, in the same one-line form, then **Coming up** from `Today.md` (events and things to do this week, like registration opening), briefly.
7. **Changes** since yesterday, if any, including new grades and comments under "From Canvas". Urgent ones (a moved due date, a rescheduled exam) go first.
8. **Exams**: a countdown for each upcoming exam.
9. **Clippings**, if `Today.md` has the section: say in one line what was filed, so a wrong guess gets noticed. If Oso couldn't place some clips, list them and ask which course each belongs to (or none); when he answers, call `file_clip` for each. A book that went to the wrong course: `move_book`.
10. **Focus**: one or two sentences on what to work on today, for about how long, and why, from **Where study time should go** in `Today.md` (weight, proximity, readiness, his goal). Do not pad. When an important exam or deadline, in a course whose grade needs attention or where readiness says he isn't ready, collides with a social or optional event (Heads up names these), say so plainly and suggest the trade-off with its reasons: the grade, the readiness, the practice results. For example: "Physics Exam 2 is tomorrow, you're at 78% in the course, and your last practice quiz on its topics was 60%. Consider skipping tonight's mixer to work on forces and energy." Suggest; he decides. Never suggest skipping a class, work, or anything he has committed to others, and never moralize.
11. **Your feedback**, if `Today.md` has it: one line each, saying what he asked for is in Oso now.
12. **Your rules**, if `Today.md` has it: one line each, what a rule of his did or why it couldn't.
13. Any **connection** problem from `Today.md`, in the same plain words it uses; a Canvas sign-in request goes first.

## Canvas topics (when Today.md says assignments are not yet matched to topics)

Before writing the briefing, for each course with unmatched assignments: call `canvas_info` with `untagged`, decide which of the course's topics each assignment covers from its name and group (a homework titled "HW 4: Newton's laws" covers "Newton's Laws"; an assignment that covers no listed topic, like a syllabus quiz, gets none), and save with `tag_assignments`. Leave an assignment out if you can't tell; it will come up again. Don't mention this in the briefing.

## Rules

- Short by default. Skip empty sections. Expand only if asked.
- Honest, not encouraging: describe readiness and standing as `Today.md` states them, lead with what's behind, and no praise the numbers don't show.
- Never invent an item, a date, or a weight that is not in `Today.md`.
- Link each item to its Canvas page when a link is present.
- For the Sunday review, add what was completed last week and the total load for the coming week, then the practice-habits note below.

## Practice habits (Sunday review only)

1. Call `practice_habits`. If `enough_data` is false, skip this part entirely.
2. Write three to five plain sentences about how he practices, using only what the numbers show: how far ahead of exams he started practice quizzes, whether he retests topics he missed and whether the retests go better, whether scores in each course are rising or fading, and whether his practice goes to the courses whose grades and upcoming work need it. Name the number behind each claim ("first practice quiz for Exam 1 came 1 day before it"). Describe what he did, never what kind of person he is; no "procrastinates", "lazy", or "great job". If a number does not support a sentence, leave the sentence out.
3. Call `save_habits_summary` with those sentences, and put the single most useful one in the briefing.
