# Learner profile: phased plan

Temporary planning document. Delete it when the last phase ships.

## Goal

Oso is a tutor, so it has to know what the student knows, what he doesn't, and how he studies. Today it knows his deadlines and grades but nothing about his understanding or habits. This plan adds a learner profile built from the two concrete sources Oso has: his notes and his test results (practice quizzes and checks of his own work). It is used to aim practice at his weak spots, to warn him in the morning briefing when an exam is coming and he isn't ready, and to describe his practice habits over time.

Oso does not mine his chats. How long he studied or how often he asked about something is not evidence of understanding; test results are. Topics he never raises are not mistaken for mastery: every course's topic list comes from its syllabus, so a topic with no test results is "untested" and goes to the front of the next quiz.

This is not a "second brain" for course content. Oso does not rewrite or synthesize his notes. The profile is about the student, not the material.

## Principles

- **Facts first, conclusions second.** Everything starts as a dated, factual record (a quiz answer or a check of his work). Summaries are computed from those records, and every claim in a summary points back to the records behind it.
- **Describe behavior, never character.** "Started the last three problem sets the night before they were due," not "procrastinates."
- **His to read and correct.** Readable summaries live in his vault under `Oso/Profile/`. Raw records live in Oso's database. If a summary is wrong, he can say so and Claude corrects the underlying record.
- **Measured, not guessed.** Numbers (scores, timings, counts) are computed by the service in plain Python. Claude is used only where judgment is unavoidable: tagging a question's topic and classifying a mistake, and writing the weekly habits summary from computed numbers.
- **Cheap on his plan.** Recording happens inside the quiz and check commands he is already running; nothing re-reads chats.
- **Fresh start clears it.** `oso fresh-start` deletes the profile along with everything else.

## Where things live

| What | Where | Who writes it |
| --- | --- | --- |
| Raw records: quizzes, questions, answers, checks | Oso database (`oso.sqlite`), new tables | Oso tools called by the skills |
| Topic list per course | Oso database, seeded from the syllabus at `/create-course` | `/create-course`, then quizzes and checks as new topics appear |
| Per-course understanding summary | `Oso/Profile/<course>.md` in the vault | The service, regenerated on every check |
| Weekly practice-habits summary | `Oso/Profile/Habits.md` in the vault | A weekly Claude run, from computed numbers |
| Readiness flags | `Today.md` (new section) and the morning briefing | The service |

## Phase 1: Quiz records

**Status:** built and tested; waiting on a real quiz in Cowork after the next release to confirm the rows (`oso profile --raw`).

The foundation. Every quiz Oso gives is recorded in detail.

**Recorded per quiz session**
- course, topics covered, source notes used
- when the quiz was handed out and when answers were submitted (the gap is completion time; it includes any breaks, since a chat has no stopwatch)
- number of questions, score, whether it was a retake of an earlier quiz, which earlier quiz
- requested size and focus (for example "5 questions on kinematics")

**Recorded per question**
- topic and theme (theme is the finer grain: topic "kinematics", theme "projectile motion")
- question type (multiple choice, short answer, worked problem, conceptual)
- difficulty (easy, medium, hard, as Claude judged when writing it)
- result: right, partly right, wrong, skipped
- attempts on that question and whether a hint was given
- for anything not fully right, the kind of mistake: concept gap, calculation slip, misread question, incomplete
- time the answer arrived

**Built**
- Database tables for quiz sessions, questions, and attempts.
- Oso tools: `start_quiz` (returns a quiz id and records the handout time and questions), `record_answers` (results per question, attempts, hints, mistake kinds), `finish_quiz`.
- The quiz skill calls them: start when the questions are shown, record when he answers, finish after grading. Retakes link to the earlier quiz.
- A plain-text summary line after grading stays as it is today; the recording is invisible to him.

**Done when**
- Tests cover recording, retakes, partial results, and a quiz abandoned halfway (handed out, never answered).
- A real quiz in Cowork produces correct rows (checked with a small `oso profile --raw` dump).

## Phase 1b: Quiz window (planned, not yet approved to build)

A formal way to take quizzes outside the chat, so timing is exact and answers stay hidden until he submits.

**How it works**
- He asks Claude for a quiz in Cowork as today. Claude writes it, including an answer key for multiple-choice questions, and records it with `start_quiz`. The key is stored by Oso and never shown in the chat.
- Oso opens a quiz window on his laptop (the same kind of window as `oso settings`; Oso's tools already run on his computer, so they can open it). The window shows one question at a time with a timer per question.
- Multiple choice is graded instantly by Oso against the key. Typed answers are saved. When he submits, the window tells him to go back to the chat, where Claude grades the typed and written answers and records the results.

**Written work: labeled pages, submitted at the end**
- For worked problems he writes on paper or on the reMarkable, one or more pages per question, with the question number in the top corner of each page.
- When he submits, the window offers **Add written work**: pull the quiz notebook from the reMarkable if it is plugged in, or pick a scan or photo file (paper work scanned with a phone).
- Oso renders the pages and Claude reads each page's corner label to match it to its question, then grades the work. A page without a readable label is shown to him to assign.
- This keeps the window independent of the tablet: paper scans work the same way.

**reMarkable details**
- Oso can download notebooks over the tablet's USB connection on demand, as it already does; the quiz window would use the same connection. It cannot erase or edit a notebook over USB, so a "clear the page after each question" flow is not possible; a fresh page per question is the equivalent.
- Optionally, Oso can upload a quiz to the tablet as a PDF with the questions and room to work, so he writes his answers on the questions themselves.

**Recorded, in addition to Phase 1**
- exact time per question (from the window), time to first answer, changes of answer before submitting
- for written work, the page images linked from the quiz record

**Done when**
- Tests cover the key staying hidden, instant grading, timing, and matching labeled pages to questions.
- A real quiz taken in the window, with one written answer from the tablet and one from a paper scan, grades correctly.

## Phase 2: Check-my-work records and topic lists

Checks of his own work are the second scored source.

**Recorded per check**
- course, topic and theme
- result: correct, or where the first mistake was
- the kind of mistake (same categories as quizzes)
- hints given before he got it right, and whether he asked for the full solution
- time

**Topic list per course**
- Seeded by `/create-course` from the syllabus schedule (week-by-week topics are usually listed) and shown to the student for confirmation with the rest of the syllabus facts, including which exam covers which topics when the syllabus says so.
- Quizzes and checks tag against this list, adding a topic only when nothing fits.

**Built**
- A `record_check` tool, called by the check skill after it responds.
- Topic tables, the `/create-course` step that fills them, and topic matching shared by quizzes and checks.

**Done when**
- Tests cover check recording, topic matching, and new-topic creation.
- `/create-course` on a real syllabus produces a sensible topic list with exam coverage.

## Phase 3: What he knows

Turn the records into a per-topic picture.

**Computed per topic (plain Python, no model)**
- accuracy across quizzes and checks, weighted toward recent attempts
- number of questions seen, last practiced date
- trend (improving, steady, slipping)
- most common mistake kind
- state: **strong**, **shaky**, or **untested**, with thresholds in settings (starting point: strong at 80% or better over at least 6 recent questions; untested below 3 questions)

**Built**
- `Oso/Profile/<course>.md` regenerated on every check: topics grouped by state, each with its numbers and links to the quizzes and checks behind them.
- `get_profile` tool returning the same for a course.
- Quiz and study-guide skills read it and aim at shaky and untested topics first, with a few strong ones for retention. Default quiz mix: about 60% shaky, 25% untested, 15% strong.

**Done when**
- Tests cover state changes as records accumulate and decay with time.
- A quiz requested with no topic leans toward his weak topics.

## Phase 4: Readiness in the briefing

Combine the profile with the deadlines Oso already knows.

**Rules (thresholds in settings)**
- An exam within 7 days, and any of:
  - no practice quiz on the exam's topics yet
  - exam topics still shaky or untested
  - last quiz on those topics below 70%
  - scores on the exam's topics slipping over the last two quizzes

**Built**
- A "Readiness" section in `Today.md`, one line per flag, specific: "Physics exam Friday (3 days). Last kinematics quiz 55%; projectile motion untested."
- The briefing skill puts readiness flags right after "Due today."

**Done when**
- Tests cover each rule firing and not firing.

## Phase 5: Practice habits

The slow-moving picture, from test records only. Weekly, once there are a few weeks of records.

**Computed weekly (plain Python)**
- **Lead time:** for each exam, how many days before it his first practice quiz on its topics came.
- **Follow-through:** how often a topic he missed gets retested within a week, and whether the retest improves.
- **Trend:** score trend per course across the semester; whether early strength holds or fades.
- **Allocation:** practice per course next to the course's current grade and upcoming weight. Flags heavy practice on a strong course while a weaker one goes untested.
- **Pace:** completion time per question over time, by topic.

**Built**
- `Oso/Profile/Habits.md`, rewritten weekly: a short narrative written by Claude from the computed numbers (each sentence citing the number behind it), followed by the numbers themselves.
- Runs as part of the Sunday review scheduled task, which already exists in the briefing skill.

**Done when**
- Tests cover each metric on synthetic records.
- The narrative never states anything the numbers do not show (checked on sample data).

## Phase 6: Wrap-up

- README: a short section on the profile, where it lives, and how to correct it.
- `oso fresh-start` clears the profile tables and `Oso/Profile/`.
- Settings window: the readiness and mastery thresholds.
- Delete this document.

## Decisions needed before starting

1. **Who sees the profile.** Only your son, in his vault, or should a weekly summary also reach you?
2. **Thresholds.** The starting numbers above (80% strong, 70% quiz warning, 7-day exam window) are placeholders.
