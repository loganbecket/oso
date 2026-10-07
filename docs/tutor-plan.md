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

## Phase 4: Time where it's needed

- **Goals:** the target grades and priorities he states are kept per course.
- **How much attention each course needs:** worked out from topics needing focus, how close the next exam is, the current grade against his goal, and the weight of upcoming work.
- **The study plan** puts study blocks on the Oso calendar in proportion, around what else is on his schedule (once the school email and GroupMe plan is in, that includes clubs and events).
- **The briefing's focus line** uses the same: what to work on today and for about how long, and why.

**Done when**
- Tests cover the attention ranking from sample courses and the plan's time split following it.

## Phase 5: How he learns

- A note in his profile, `How I learn`, built from his stated preferences and from what has worked (explanations he understood the first time versus ones that needed another try), each with its evidence. Claude reads it before explaining anything, and he can correct it.

**Done when**
- Tests cover preferences recorded and shown, and corrections.

## Phase 6: Wrap-up

- README: what Oso learns from conversations, where it shows, how to correct it, and the School project instructions to paste.
- `oso fresh-start` clears the conversation notes with the rest of the profile.
- Release. Delete this document.

## Limits

- **Consistency is the risk.** Claude notes signals only when it recognizes them in the moment. The project instructions make that the default in every School chat, but a casual chat outside the project, or a long tangent, can miss things. Tests remain the backstop: a missed confusion still shows up in practice results.
- **Quotes are his words.** They stay in his own database and vault, used only for his tutoring.

## Decisions

Defaults below; easy to revisit.

1. **Weight of conversation evidence:** confusion or a misconception counts like a wrong practice answer; explaining it well counts like half a right one; nothing from conversation alone can make a topic solid.
2. **Solid** needs a good explanation in his own words plus strong recent results; **maintaining** needs solid held for three weeks.
3. **Goals are only what he states**; Oso never assumes a target grade.
