# Where You Stand

Oso keeps an honest record of what you know in each course, topic by topic, built from your results. It also tracks your grades and tells you what you need to reach the grade you want.

## What it's for

It's easy to feel ready because you've read something or had it explained. Oso goes by evidence instead: quizzes, checks of your own work, and your graded work in Canvas. It knows which topics are weak, which are untested, and which are solid, so explanations, quizzes, study guides, and study plans all aim at what needs work. It also warns you when an exam is close and you aren't ready.

## How to use it

- "What am I weak at in physics?" or "How am I doing in calculus?" Claude gives you your gaps first, then what you're practicing, then what's solid, with the evidence for each.
- "What do I need on the final to get an A in chemistry?" Claude shows your current percent, how much of the grade it rests on, and the average you need on the rest. It also tells you if the target is already secured or out of reach.
- "Why did I lose points on HW 4?" With Canvas connected, Claude explains your instructor's comments in plain words.
- "Question 3 on my last physics quiz was actually right." Claude finds the record, confirms it with you, and fixes it. A grade changes only if the grading criteria support it.
- "Delete that quiz" (a test run, say). Claude tells you which quiz it is and deletes it only after you confirm.

## How a topic is rated

Each topic in a course is at one stage:

- **Untested**: no results yet. It's never assumed known.
- **Needs focus**: your results show a weak spot.
- **Explained**: Claude has explained it, but you haven't shown it yet.
- **Practicing**: mixed or improving results.
- **Solid**: results show you know it.
- **Maintaining**: solid and holding. It gets an occasional light review.

Every quiz question and every check of your work counts: the topic, whether you got it right, the kind of mistake, how long it took, and whether you needed a hint. With Canvas connected, your real graded work on a topic counts too. Claude also quietly notes what you show in study chats: confusion, a specific wrong idea, explaining something correctly in your own words, how you learn best, and the grades you're aiming for. Nothing you say can make a topic solid on its own. Only results can.

## Getting the most out of it

- Take short quizzes often. More results means more accurate ratings.
- Retest the topics you missed. The record shows whether you follow up.
- Tell Claude your grade goals ("I want a B+ in chemistry"). The briefing and study plans weigh them.
- If a rating looks wrong, say so and make your case. Claude looks at the record fresh.
- Read the weekly practice-habits note (in Sunday's briefing): it's built from numbers, not opinions.

## Good to know

- **Honest, not flattering.** Claude can't declare a topic solid or a grade good. Oso computes those, and Claude reports them as they are, gaps first, with the evidence for anything positive. No unearned praise.
- **Grading criteria come first.** Every question Claude grades has its criteria written before you answer. Pushback changes a grade only if your answer meets the criteria.
- **Practice versus real work.** If your practice scores run well above your graded work on the same topics, the briefing says so and practice gets harder.
- **Practice habits.** Each Sunday, once there are a couple of weeks of results, Claude writes a short note on how you practice: how early you start before exams, whether you retest what you missed, whether scores are rising or fading, and whether practice goes where it's needed. It describes what you did, never what kind of person you are.
- **Where it's kept.** Summaries are in `Oso/Profile/` in your vault: one note per course plus `Habits.md` and `How I learn.md`. The raw records stay in Oso's database on your computer. `oso profile --raw` lists every quiz, question by question.
- **Grades.** With [Canvas connected](canvas.md), Oso reads your grades on its own. Without it, tell Claude a grade and it records it. The what-if math assumes ungraded items in a category count the same as graded ones.
- `oso fresh-start` clears the whole record.
