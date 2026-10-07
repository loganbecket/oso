# A study partner that knows him: phased plan

Temporary planning document. Delete it when the last phase ships. This is a feature release: it ships as the next 0.x.0 when its turn comes (after the settings launcher, v0.7.0, and school email and GroupMe, v0.8.0, unless the order changes).

## Goal

Oso is, in the end, one ongoing conversation between the student and Claude, with tools that give Claude context. For it to be a real study partner, Claude has to know him: which topics he is solid on and which he keeps struggling with, the specific things he misunderstands, how he learns best, and what he is aiming for. Every turn of every study conversation is a chance to learn that.

Today Oso learns only from quizzes and checks of his work. This plan adds what he shows in conversation ("I'm really confused about why we need an integral here"), turns all the evidence into a trajectory per topic (struggling, explained, practicing, solid, maintaining), and has every part of Oso act on it: explanations, quizzes, study guides, the study plan, and the briefing. When a topic is fixed, the pressure eases off.

## Principles

- **Noted in the moment.** Oso can't read conversations afterward, so Claude notes what it sees as it happens, quietly, in a sentence: never announced, never interrupting.
- **Conversation steers, tests confirm.** What he says in conversation is real evidence, but weaker than results. Confusion moves a topic toward focus right away; explaining it well in his own words counts for something; only practice results can make a topic solid.
- **Oso computes the trajectory, not Claude.** Claude is not good at noticing a trend across many past conversations. Oso keeps the dated evidence and works out each topic's stage and next step in plain arithmetic, so Claude starts every conversation knowing where things stand.
- **Specific, not vague.** A misconception is kept as what he actually believes ("thinks the integral is needed whenever a rate is given"), so a quiz can test exactly that, and it stays open until he shows it is fixed.
- **His to see and correct.** Everything shows in his profile notes in the vault, with the evidence; if something is wrong, he says so and Claude fixes the record.
- **Honest before encouraging.** Language models lean toward flattery, and false praise is worse than none: it tells him a topic is handled when it isn't, so he stops working on it. Wherever possible the judgment is taken out of Claude's hands and made by Oso from evidence; where Claude must judge (grading written work), it judges against criteria fixed in advance; and Oso checks practice against real grades to catch leniency nobody noticed (Phase 4).

## Phase 1: Noting what he shows in conversation

**What Claude notes** (one Oso tool, `note_signal`), each with the course, the topic (from the course's topic list), and his words where they show it:

| Kind | Example |
| --- | --- |
| Confused | "I don't get why we need an integral here" |
| Misconception | believes something wrong; kept as the wrong idea itself |
| Basic question | asks something a topic he's been taught should cover |
| Explained it well | explains the idea correctly in his own words, unprompted or when asked |
| Solved it unaided / needed help | works a problem through in chat, with or without hints |
| Preference | "worked examples help me more than definitions" |
| Goal | "I need at least a B+ in physics" |

- Repeats within one conversation are folded into one note.
- **Making Claude do it every time:** the same short instruction in four places, so it applies in casual chats as well as commands: the School project's instructions in Cowork (the text to paste is in the README), the vault's instructions file, every study command, and the tool's own description.

**Done when**
- Tests cover storing each kind, matching topics, folding repeats, and misconceptions kept as open.

## Phase 2: A trajectory for every topic

**Stages**, worked out from all the evidence (conversation notes, practice quizzes, checks of his work, graded Canvas work), most recent counting most:

| Stage | Means | Next step |
| --- | --- | --- |
| Untested | no evidence yet | find out (a few questions) |
| Needs focus | recent confusion, an open misconception, or weak results | explain, then check understanding |
| Explained | Claude has explained it since the confusion; not yet shown | check understanding (ask him to explain it back, or a quick question) |
| Practicing | shown some understanding; results mixed or few | practice |
| Solid | explained well and recent results strong | review now and then |
| Maintaining | solid and stable over weeks | light review only |

- New confusion or a poor result moves a solid topic back; a topic left alone for weeks drifts from maintaining to due for review.
- A misconception closes when he gets that idea right afterward (a correct answer on a question aimed at it, or explaining it correctly).
- The per-course profile notes show each topic's stage and next step with its dated trail: "confused Oct 3 ('…'); explained Oct 3; quiz Oct 5, 3 of 3; quiz Oct 8, 4 of 4 → maintaining."
- Today's strong / shaky / untested ratings become part of this; the thresholds stay settings.

**Done when**
- Tests walk topics through every stage and back (the integral example end to end), misconceptions opening and closing, and drift with time.

## Phase 3: Every conversation starts from it

- **Explain:** Claude checks the topic's stage, open misconceptions, and his preferences before answering, explains the way that works for him, and for a topic in focus ends by asking him to put it in his own words or answer one quick question, which becomes evidence.
- **Quiz:** questions follow the next steps: most on topics needing focus or practice, aimed at open misconceptions (with wrong answers built from his actual misunderstanding), fewer on solid topics, and occasional review of maintained ones.
- **Check my work, study guides, flashcards:** weight toward the same topics and misconceptions.
- **Easing off:** topics that reach solid stop dominating practice and the briefing; Claude says so when it happens ("integrals look solid now; I'll stop pushing them").

**Done when**
- Tests cover the profile Claude receives (stage, next step, misconceptions, preferences) and the quiz mix following next steps.

## Phase 4: Honest feedback

Sycophancy is the failure that would quietly break the tutor. "You're doing great!" when he is merely on track builds false confidence, and he puts his effort in the wrong places. An instruction alone won't hold: the pull toward encouragement creeps back in over long conversations and when he pushes back. So this phase uses several layers, each catching what the one before misses.

### 4.1 Oso decides the verdict; Claude reports it

- Whether a topic is untested, needs focus, practicing, solid, or maintaining is computed by Oso from the evidence (Phase 2), never declared by Claude. Claude cannot mark a topic solid; only results can.
- Oso supplies a plain status line per topic and per course ("projectile motion: 2 of 5 on the last two quizzes; open misconception about the horizontal velocity; needs focus"). When Claude talks about where he stands, it gives that line and its evidence, in its own words but without upgrading it.
- Course-level standing (current grade, the grade needed for his stated goal, readiness for the next exam) comes from Oso's numbers, the same way.

### 4.2 Words tied to evidence

Claude's description of how he is doing must match the measured stage. The standing rule includes this table:

| Stage | Words Claude may use | Words it may not |
| --- | --- | --- |
| Needs focus | weak spot, not there yet, needs work, struggling with | getting there, almost, close |
| Explained | explained, not yet shown | understands, got it |
| Practicing | improving (only if the trend shows it), mixed, on track | great, strong, mastered |
| Solid | solid, reliable, strong (with the evidence) | mastered, perfect, nothing to worry about |
| Maintaining | solid and holding | done with it, never needs review |

- **Any positive claim names its evidence**: "you got all four kinematics questions right on Tuesday and Thursday" rather than "you're good at kinematics."
- **Gaps first.** When reporting results or standing, Claude leads with what is wrong or weak, then what is right, then the next step.
- **No reflexive praise.** No "great question," "good job," "awesome," "you've got this," or exclamation-point encouragement. Acknowledging real progress is fine when the numbers show it, stated plainly ("that's up from 40% to 75% in a week").
- **Wrong is wrong.** A wrong answer is called wrong, with what is wrong about it; "partly right" only when the grading criteria say part of it earns credit; never "close" for an answer that isn't.

### 4.3 Grading decided before he answers

- When Claude writes a quiz, it also writes, for every question that it will grade itself (typed and written work), the expected answer and the grading criteria: what earns full credit, what earns partial credit, and the common wrong answers and why they are wrong. Oso stores these with the quiz, hidden from him, alongside the multiple-choice key.
- When grading, Claude works from those stored criteria (Oso hands them back with his answers) and records which criterion each answer met or missed. A confident, long, or sympathetic answer earns nothing the criteria don't give it.
- Multiple choice stays graded by Oso itself, with no judgment involved.
- **Pushback doesn't change grades.** If he argues a grade, Claude re-checks against the criteria and changes it only if the criteria support it, saying which one; the change and its reason are recorded. "I meant that" or "that's basically the same" is not a reason.
- Checks of his own work follow the same rule: the first mistake is named precisely, and "right" means right.

### 4.4 A second grader, now and then

- For a sample of quizzes (every fifth, and any written-work quiz scoring 90% or more), the examiner agent regrades his written answers from the stored criteria without seeing the first grades.
- Disagreements are recorded. Oso tracks how often the first grading was more generous than the second; if it is consistently more generous, the profile and `oso doctor` say so and the grading instructions tighten. The second grade counts when they differ.

### 4.5 Reality check against real grades

The strongest guard, because it catches leniency nobody noticed, including Claude.

- For each course, Oso compares his practice results with his real graded work on the same topics (Canvas homework, quizzes, and exams, tagged with topics as they already are).
- If practice consistently runs well above reality (by 15 points or more across at least two real assessments), Oso flags it in the profile note and the briefing: "Your practice scores in Physics run about 20 points higher than your real ones; practice is too easy." From then on, quizzes in that course get harder (more worked problems and multi-step questions, harder distractors, no hints on the first attempt), and topics don't count as solid until practice and real results agree.
- The flag clears when practice and real grades line up again.

### 4.6 His confidence against his results

- The quiz window asks, for each question, how sure he is (sure, think so, guessing), with one click.
- Oso compares confidence with correctness: being sure and wrong is the most important thing a quiz can find. Those questions are marked in the results, their topics move toward focus, and a pattern of overconfidence in a course is called out in the profile note ("you were sure on 6 answers this week and 3 were wrong, all on forces").
- Guessing and right counts as less evidence than knowing and right.

### 4.7 Difficulty that means something

- Claude labels each question easy, medium, or hard when writing it; Oso checks the labels against results. If he gets nearly every "hard" question right, the labels are inflated: the quiz instructions are told to write harder hard questions, and the profile notes it.
- Topics are only called solid on evidence that includes medium or hard questions, not easy ones alone.

### 4.8 The standing rule

The same short rule goes in the four places the conversation-notes instruction goes (the School project instructions in Cowork, the vault's instructions file, every study command, and the profile tool's description):

> Be a direct, honest tutor. Report where he stands from Oso's measured status, never your impression, and name the evidence for anything positive. Lead with gaps and mistakes. No unearned praise, no "great question," no softening a wrong answer. Grade against the stored criteria; don't change a grade under pushback unless the criteria support it. Say plainly when you're unsure.

The weekly habits note and the briefing follow the same rule; the habits note already describes behavior, not character.

**Done when**
- Tests cover: verdicts coming only from Oso's computation (a conversation note alone never makes a topic solid); grading criteria stored at quiz creation and returned with his answers; a regrade under pushback recorded with its reason; the second-grader sample and the generosity tally; the practice-versus-reality flag appearing at the threshold and clearing; confidence recorded in the quiz window and "sure but wrong" moving a topic toward focus; difficulty labels checked against results; and the standing rule present in every study command.
- A review of real conversations after a few weeks finds no unearned praise and status descriptions that match the measured stages.

## Phase 5: Time where it's needed

- **Goals:** the target grades and priorities he states are kept per course.
- **How much attention each course needs:** worked out from topics needing focus, how close the next exam is, the current grade against his goal, and the weight of upcoming work.
- **The study plan** puts study blocks on the Oso calendar in proportion, around what else is on his schedule (once the school email and GroupMe plan is in, that includes clubs and events).
- **The briefing's focus line** uses the same: what to work on today and for about how long, and why.

**Done when**
- Tests cover the attention ranking from sample courses and the plan's time split following it.

## Phase 6: How he learns

- A note in his profile, `How I learn`, built from his stated preferences and from what has worked (explanations he understood the first time versus ones that needed another try), each with its evidence. Claude reads it before explaining anything, and he can correct it.

**Done when**
- Tests cover preferences recorded and shown, and corrections.

## Phase 7: Wrap-up

- README: what Oso learns from conversations, where it shows, how to correct it, how it keeps feedback honest, and the School project instructions to paste (conversation notes and the honesty rule together).
- `oso fresh-start` clears the conversation notes with the rest of the profile.
- Release. Delete this document.

## Limits

- **Consistency is the risk.** Claude notes signals only when it recognizes them in the moment. The project instructions make that the default in every School chat, but a casual chat outside the project, or a long tangent, can miss things. Tests remain the backstop: a missed confusion still shows up in practice results.
- **Honesty can't be fully tested in advance.** The rule, the evidence-tied words, and the stored criteria shape Claude's behavior, but only real conversations show whether flattery still slips through. The practice-versus-reality check is the measurable backstop, and a review of real conversations after a few weeks is part of finishing.
- **Quotes are his words.** They stay in his own database and vault, used only for his tutoring.

## Decisions

Defaults below; easy to revisit.

1. **Weight of conversation evidence:** confusion or a misconception counts like a wrong practice answer; explaining it well counts like half a right one; nothing from conversation alone can make a topic solid.
2. **Solid** needs a good explanation in his own words plus strong recent results; **maintaining** needs solid held for three weeks.
3. **Goals are only what he states**; Oso never assumes a target grade.
4. **Practice-versus-reality flag** at 15 points or more across at least two real assessments.
5. **Second grader** on every fifth quiz and on any written-work quiz scoring 90% or more; its grade counts when they differ.
6. **Confidence per question** in the quiz window: one click, three choices, never required to submit.
