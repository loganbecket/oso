# Canvas through his own sign-in: phased plan

Temporary planning document. Delete it when the last phase ships. This is a feature release: it ships as **v0.2.0** (phases can be released together or as 0.2.x fixes along the way).

## Goal

The school does not let students create Canvas access keys, so today Oso only gets due dates from the Canvas calendar feed. Everything else that matters for tutoring (scores, missing work, instructor comments, quiz results, current grades, announcements, files) is invisible to it.

This plan has Oso read Canvas the same way his browser does: he signs in once in an Oso sign-in window, Oso keeps that signed-in session, and on every check it reads his own data from Canvas, read-only. When the session expires, Oso tells him and one click brings the sign-in window back.

The payoff is the tutoring this whole project is for: "Exam 2 is Thursday and your homework average on its topics is 64%. Want a study plan and a practice test?"

## Principles

- **Read-only, his own data.** Oso only reads what he can already see in Canvas. It never submits, posts, or changes anything.
- **No password stored.** Oso never sees or keeps his school password. He signs in himself, including any two-step check; Oso keeps only the resulting session, in the operating system's credential store, like the feed address today.
- **Re-sign-in only when needed.** No reminders on a timer. Oso notices the moment Canvas stops accepting the session and asks then.
- **Oso reads, Claude interprets.** Canvas already returns tidy, structured data, so Oso stores it directly in its database with no Claude usage. Claude is used only for judgment: tagging each new assignment with the syllabus topics it covers.
- **The existing Canvas code is reused.** Oso already has the code to read grades, assignments, announcements, and files with an access key. This plan swaps the access key for the signed-in session and widens what is read.
- **Fails quietly and plainly.** If Canvas cannot be read, the calendar feed keeps due dates flowing and the briefing says in one line what is wrong.

## Phase 0: Confirm it works at his school

A check, not a build. Decides whether the rest goes ahead.

- He signs in to Canvas in his browser, then opens `https://<his school>.instructure.com/api/v1/users/self/courses?include[]=total_scores`.
  - **Pass:** the page shows text full of his course names and scores. The session approach works.
  - **Fail:** an error or a login page. We stop and rethink.
- Note how he signs in (straight to Canvas, or through a school sign-in page) and whether there is a two-step check.
- Skim the school's acceptable-use policy for anything about automated access.
- Record the results here.

## Phase 1: The sign-in window

**Built**
- `oso connect-canvas` (and a **Connect Canvas** button in `oso settings`) opens a small window showing his school's Canvas sign-in page. He signs in as usual, including any two-step check.
- When Canvas's dashboard loads, Oso takes the session from that window, checks it works by reading his course list, stores it in the credential store, and closes the window with "Canvas connected."
- The window is a built-in browser view (Windows already has the component it needs; macOS and Linux have equivalents), so nothing extra to install.
- `oso disconnect-canvas` forgets the session.
- The Canvas address is asked once (or taken from the feed address, which already contains it).

**Done when**
- Tests cover storing, reading, and forgetting the session, and refusing a session that cannot read the course list.
- He connects for real on his laptop (after Phase 0 passes).

## Phase 2: Noticing expiry and getting him back in

**Built**
- On every check, if Canvas refuses the session, Oso marks Canvas as needing sign-in and:
  - shows a Windows notification, "Canvas needs you to sign in again," that opens the sign-in window when clicked (once per expiry, not every 15 minutes)
  - puts the same line in `Today.md` (so the morning briefing carries it) and in `oso doctor`, until he signs in
- Oso records when each session started and when it expired, so we learn how long sessions last at his school and can tune from facts.
- Due dates keep coming from the calendar feed while Canvas is disconnected.

**Done when**
- Tests cover expiry detection, one notification per expiry, and the lines in `Today.md` and `oso doctor`.

## Phase 3: Reading Canvas

On every check, while connected, Oso reads and stores:

| What | Used for |
| --- | --- |
| Courses, with current grade and the grading scheme (letter cutoffs) | Grades, what-if, the dashboard |
| Assignment groups and their weights | Grade math (replaces syllabus guesses when Canvas has them) |
| Assignments: title, due date, points, group, type, whether it is a quiz | Deadlines (merged with the feed and syllabus as today), topic tagging |
| His submissions: score, grade, submitted when, late, missing, excused | Grades, missing-work warnings, readiness |
| Instructor comments on his submissions | Feedback Claude can explain |
| Quiz results: score, attempts, and per-question results where the instructor allows students to see them | Topic ratings, readiness |
| Announcements | Already mirrored into the course folder; kept |
| Course files | Already mirrored into the course folder and made searchable; kept |

**Built**
- The existing Canvas reader switched to the signed-in session, widened to the table above, and storing into new database tables (raw Canvas records kept alongside, so nothing has to be re-read to answer a new question later).
- Only changed things are re-read where Canvas allows it, to keep each check quick.
- New and changed grades and comments show up in `Today.md` under changes ("Physics: Homework 4 graded, 7/10, with a comment").

**Done when**
- Tests replay recorded Canvas responses for every item in the table.
- A real check on his laptop fills the tables (shown by an `oso canvas --raw` dump).

## Phase 4: Claude's view of Canvas

**Built**
- One tool for Claude, `canvas_info`, answering by course: grades and standing, recent scores, missing or late work, instructor comments, quiz results.
- Topic tagging: when new assignments appear, Claude tags each with the syllabus topics it covers (once per assignment, during the next briefing or course chat), stored by Oso. Assignments it cannot place are left untagged rather than guessed.
- The grades and explain commands use it ("why did I lose points on Homework 4?" reads the instructor's comment).

**Done when**
- Tests cover the tool's answers and storing tags.

## Phase 5: Canvas results in the profile and the briefing

**Built**
- Graded Canvas work becomes evidence in the learner profile, next to practice quizzes and checks: each tagged assignment's score counts toward its topics.
- Readiness, for each exam within the readiness window, adds:
  - his graded homework and quiz average on the exam's topics, flagged below the warning threshold
  - missing or late work on those topics
- The morning briefing turns a flag into an offer: a study plan working back from the exam and a practice test on the weak topics, both existing commands.
- Missing work is flagged on its own, any day: "Physics: Homework 5 is marked missing."

**Done when**
- Tests cover Canvas evidence in topic ratings and each new readiness rule firing and not firing.

## Phase 6: Wrap-up

- README: connecting Canvas, what Oso reads, what happens when the sign-in expires.
- `oso fresh-start` keeps the Canvas connection (it is a connection, like the calendar) and clears everything read from Canvas; the next check reads it again.
- Settings window: Connect / Disconnect Canvas, and whether to show the Windows notification.
- Release as v0.2.0. Delete this document.

## Decisions needed before starting

1. **Do real Canvas grades count toward topic ratings**, or only feed the readiness warnings? (Recommendation: count them, weighted the same as a practice result, since a graded homework is real evidence.)
2. **The Windows notification**: on by default, or briefing line only?
3. **Phase 0 timing**: he can do the one-minute browser check whenever he next has Canvas open.
