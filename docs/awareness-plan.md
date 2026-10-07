# School email, GroupMe, and the whole week: phased plan

Temporary planning document. Delete it when the last phase ships. This is a feature release: it ships as **v0.8.0** (after the settings-launcher release, v0.7.0).

## Goal

A tutor that only knows deadlines can't give good advice. Most of what competes for the student's time arrives elsewhere: email from instructors, departments, and the school (a moved deadline, registration opening Monday), and GroupMe messages from clubs, fraternities, and church groups (the meeting moved to the soccer fields at 6). Claude can look at these when asked, but nothing watches them.

This plan has Oso read the student's school email account and his GroupMe groups on every check, have Claude pick out what matters, keep it alongside his deadlines, put it on the Oso calendar, and use the whole picture in the morning briefing, so it can say: "You have an important test tomorrow in a class where you need to raise your grade, and your recent practice says you're not ready. Consider skipping tonight's mixer to fill the gaps."

## Principles

- **The school account only.** Oso reads the one email account he uses for school. His personal email is never connected. An invitation that reaches his personal account gets added when he tells Claude about it.
- **The Oso calendar is his calendar.** Everything Oso adds or changes goes on it, with where it came from in the event's notes, so he can always tell what Oso added.
- **Oso fetches, Claude judges.** Fetching mail and messages is plain downloading with no Claude usage. Obvious noise (promotions, newsletters, messages already handled from Canvas) is set aside on the laptop. Only what is left goes to Claude, in small batches, through Claude Code on the laptop, the same way handwriting is read.
- **Facts, not mail.** What Oso keeps from a message is what matters in it (a dated event, a changed deadline, an action he needs to take), with a link back to the message. Message bodies are not copied into the vault.
- **Advice, not orders.** The briefing weighs his commitments against his deadlines and readiness and suggests; he decides.

## Phase 0: Setup (one time)

- **Email:** the Google project already set up for the Oso calendar gets one more permission, read-only access to Gmail. He connects once more (`oso connect-email`, or a button in settings), signing in with his school account. Google shows an "unverified app" screen, as it did for the calendar.
- **GroupMe:** he signs in at GroupMe's developer site and copies his access token into `oso settings` (or `oso connect-groupme`). It is stored in the credential store like his other connections.

## Phase 1: School email

- On every check, Oso asks Gmail only for what arrived since the last check.
- Set aside on the laptop: Gmail's Promotions and Social categories, mailing lists he marks as noise, and Canvas's own notification emails (Oso already reads Canvas directly).
- What is left is kept as a short record per message: sender, subject, date, a trimmed copy of the text, and a link to open it in Gmail.

**Done when**
- Tests replay recorded Gmail responses: only new messages fetched, noise set aside, records kept, nothing fetched twice.

## Phase 2: Picking out what matters

- New message records go to Claude in batches, through Claude Code on the laptop. For each message Claude returns whether it matters, and if so the facts: a deadline, an event (what, when, where), a change to something already known (moved, canceled, rescheduled), or an action he needs to take (register, sign, reply), with the course or group it belongs to and how urgent it is.
- Facts are kept as **happenings** alongside his deadlines. A change updates the happening it changes rather than adding a second one. A deadline that Canvas or the syllabus already has is merged with it, not duplicated.
- Urgent ones (something moved or canceled today or tomorrow, a deadline within the urgent window) are flagged like Canvas changes today.
- No limit by default; an optional daily cap in settings, as for page reading.

**Done when**
- Tests cover extraction results being stored, a change updating its happening, a duplicate of a Canvas deadline being merged, and messages that don't matter being dropped.

## Phase 3: GroupMe

- On every check, Oso reads new messages from each of his groups since the last one it saw.
- He can mute groups that never matter (in settings, or by telling Claude).
- New messages go through the same picking-out as email, a batch per group, with the group's name as context.

**Done when**
- Tests replay recorded GroupMe responses: only new messages read, muted groups skipped, happenings created.

## Phase 4: The Oso calendar holds the week

- Events picked out of email and GroupMe go on the Oso calendar automatically, marked with their source. Changes move or cancel the event Oso added; Oso never touches an event it didn't create unless he asks.
- Claude can add, move, or remove events on the Oso calendar when he asks in chat, including invitations from his personal account ("add Saturday's tailgate, noon at the stadium").
- Oso reads the whole Oso calendar on every check (including events he or Claude added), so it knows everything on his schedule.

**Done when**
- Tests cover adding, moving, and canceling events from happenings, never editing events Oso didn't create, and reading the calendar back.

## Phase 5: The briefing weighs it all

- `Today.md` gains **Today's schedule** (classes he has entered, meetings, events, in time order) and **Coming up** (the next week's non-academic happenings and actions he needs to take, such as registration opening).
- Conflicts are flagged: an event the evening before an exam, two things at the same time, an action deadline approaching.
- The morning briefing combines the schedule with readiness and grades: when an important exam or deadline in a course that needs attention collides with a social or optional event, it says so plainly and suggests the trade-off, with the reasons (the grade, the readiness, the practice results).

**Done when**
- Tests cover the schedule sections, conflict flags, and the briefing instructions producing a trade-off suggestion from sample facts.

## Phase 6: Wrap-up

- README: connecting school email and GroupMe, what is read and what is kept, muting groups.
- Settings window and `oso doctor`: email and GroupMe connection status, last read, groups muted.
- `oso fresh-start` keeps the connections and clears happenings.
- Release v0.8.0. Delete this document.

## Later, not in this plan

- **How he actually spends his time.** Oso can know what was on his calendar but not whether he went. A later phase could learn from what he tells Claude and from the learner profile, and add it to the weekly habits note.

## Decisions

Defaults below; easy to revisit.

1. **Events from email and GroupMe go on the Oso calendar automatically**, marked with their source, rather than waiting for him to approve each one.
2. **All his GroupMe groups are read by default**; he mutes the ones that never matter.
3. **No daily cap on Claude's reading by default**, with one available in settings.
