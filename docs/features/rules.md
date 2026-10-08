# Rules

Rules let you shape Oso by saying what you want from now on. Say it once, and Oso keeps doing it.

## What it's for

Everyone wants something a little different. Maybe you want the briefing as quick bullet highlights. Maybe you always want three hours of study time on the calendar before an exam. Without rules you'd have to ask every time. With a rule, you ask once and it sticks.

There are two kinds:

- **How Oso responds.** "Give me the briefing as bullet highlights." "Start every briefing with the weather." "Keep answers to a few sentences."
- **When something happens, do something.** "When a new test date shows up, block three hours to study three days before." "Any time I get an email from the dean, block an hour within a day to deal with it."

## How to use it

Just say it in any chat, using words like "from now on," "always," "every time," or "stop doing that." Claude asks, "Want me to keep that as a rule?" Nothing is saved unless you say yes.

Before saving, Claude says the rule back in one sentence. For a "when" rule it also says when it will happen, for example "within 15 minutes of Oso seeing the new exam." If a rule could already apply (exams already on your list), Claude asks once whether to apply it to those too.

To see or change your rules:

- "What rules do I have?" or type `/oso-rules`
- "Pause the study-block rule."
- "Change the study blocks to two hours."
- "Stop adding study blocks." (pauses or deletes the rule that adds them)

## What happens after

- **How rules** take effect the next time you use the command they're about, or everywhere if they're about everything.
- **When rules** are checked every 15 minutes. A study block goes in the earliest free time that avoids your classes, everything on your Oso calendar, and your quiet hours. If that day is full, it goes on the nearest earlier day, and the briefing says so.
- **Each rule acts once per thing.** If the exam moves, its study block moves with it. If the exam is canceled, the block comes off your calendar.
- **Your briefing tells you** in a line when a rule did something, or why it couldn't (no free time, Claude not signed in on your computer).
- Rules that need judgment, like "block time to do what the email asks," are carried out by Claude in the background on your computer, using only Oso's tools.

## Getting the most out of it

- **Say it the way you'd say it to a person.** Plain words work; there's no special format.
- **Be specific about time.** "Three hours, three days before" is better than "some time before."
- **Start small.** One or two rules you'll actually notice beat ten you forget about.
- **Check the briefing line.** It's how you know a rule is working.
- **Edit freely.** Each rule is a note in your vault's `Oso/Rules` folder. If you change one by hand, Oso rereads it before it runs again.

## Good to know

- **Claude turns down what Oso can't do.** "Mine a bitcoin every time you update my calendar" gets a one-sentence no.
- **Oso's own rules win.** Oso never writes to school systems, only changes the Oso calendar and task list, reports where you stand honestly, and never edits notes you wrote. A rule that conflicts ("always tell me I'm on track") is turned down or narrowed, and Claude tells you which part and why.
- **Deleting a rule** leaves anything it already put on your calendar.
- **Fresh start erases your rules.**
