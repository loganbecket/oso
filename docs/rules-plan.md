# Rules: plan

Temporary planning document. Delete it when this ships. A feature release: the next 0.x.0.

## Goal

The student shapes Oso by telling Cowork what they want from now on. Two kinds of rules:

- **How Oso responds:** "Give me the briefing as bullet highlights." "Start every briefing with the weather."
- **When something happens, do something:** "When a new test date shows up, block three hours to study three days before." "Any time I get an email from this address, block an hour within a day to deal with it."

Rules live in the vault, take effect without any command, and are erased by a fresh start.

## Making a rule

- Claude recognizes a standing request in any conversation ("from now on", "always", "every time", "stop doing that") and asks "Want me to keep that as a rule?", the same way it offers to pass on a complaint as feedback. Nothing is saved without a yes.
- Before saving, Claude says the rule back in one plain sentence, and for a "when" rule, says when it will happen ("within 15 minutes of Oso seeing the new exam").
- A new command, `/oso-rules`, lists the rules in effect and changes, pauses, or deletes one. Claude does the same when asked in plain words ("stop adding study blocks").
- Each rule is one note in `Oso/Rules/`, written in plain words. Fresh start already deletes everything in the vault it isn't told to keep; `Oso/Rules` stays off that list.

## What Claude turns down

- No list of allowed rules. When saving, Claude decides whether Oso can actually do it with what Oso sees and the tools it has. "Mine a bitcoin every time you update my calendar" is turned down in one sentence saying Oso can't do that.
- Oso's own rules win over the student's: read-only toward school systems, only the Oso calendar is written, honest reporting of where he stands, notes he wrote are never edited. A rule that conflicts ("always tell me I'm on track") is turned down or narrowed, and Claude says which part and why.
- A "how" rule that needs something Cowork has but Oso doesn't (the weather, from web search) is fine, since Cowork does the work.

## How Oso responds

- The tool that hands each command its instructions also hands it the rules for that command and the rules for everything. Every command then follows them, with no change to each command's own instructions.
- Rules that apply outside any command (how to explain, how long answers should be) go in the vault's Claude instructions, regenerated on every sync.

## When something happens

When the rule is saved, Claude also fills in a short form the sync can follow: what to watch for, when to act, and what to do. For example: a new item whose kind is exam; three days before its date; a three-hour study block on the Oso calendar.

On every 15-minute sync:

1. The sync compares what changed (new or moved deadlines, grades, announcements, email, GroupMe, Canvas) against each rule's form. No match, no Claude.
2. A match whose action the sync can do by itself (add, move, or remove an Oso calendar event) is done right away.
3. A match that needs judgment ("block time to do what the email asks") starts Claude in the background on the student's computer, the same way Oso already reads email and transcribes handwriting, with the rule and the one thing that matched. That Claude can use only Oso's tools.
4. Each rule acts once per item. Oso keeps track of what each rule created: if the exam moves, its study block moves; if the exam is canceled, the block is removed.

The note for each rule shows when it last ran and what it did. If a rule couldn't run (Claude not signed in, the computer was off for a while, no open time found), the briefing says so in a sentence.

If the student edits a rule note by hand, the sync notices and has Claude redo the form in the background before the rule runs again.

## Done when

- Tests: a "how" rule reaching the briefing's instructions; a "when" rule firing once per new exam and not again; the block moving with the exam and removed with it; an email-sender rule firing; a rule needing Claude starting it in the background with only Oso's tools; an edited note getting a new form before it runs; fresh start erasing the rules and keeping feedback; a rule turned down for something Oso can't do; one that conflicts with Oso's own rules narrowed.
- A real run on his laptop: the briefing format rule, the test-date rule against a real exam, and an email rule.
- The spec updated.

## Decisions (Logan's)

1. **Names:** "Rules" for the folder and in Claude's wording, `/oso-rules` for the command.
2. **Picking an open time:** the earliest open slot that avoids classes, everything on the Oso calendar, and quiet hours. For "three days before," that day; if the day is full, the nearest earlier day, and the briefing says so.
3. **Existing items when a rule is saved:** Claude asks once whether to apply it to what's already there (exams already on the list).
4. **Telling him when a rule fired:** a line in the next briefing, not a notification.
5. **Release:** 0.12.0.
