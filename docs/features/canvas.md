# Canvas

Oso reads Canvas, your school's course website, so you never have to check it yourself. On its own, the calendar feed brings in due dates. Signing in to Canvas through Oso adds your grades, scores, missing work, instructor comments, course files, announcements, and messages from your instructors.

## What it's for

Canvas holds most of what your classes expect from you, but it's spread across a dozen pages per course, and it never tells you what changed overnight. Oso reads it every 15 minutes and pulls out what matters: a new due date, a moved one, a new grade, a comment from your instructor, a file you'll need, or "class is canceled today." Then it tells you once, in your morning briefing or on your calendar.

## How to use it

You don't do anything day to day. Once Canvas is connected:

- **Due dates** show up in your deadlines list, the briefing, and `Today.md`. A moved due date or a new graded item due soon goes straight onto your Oso calendar. See [Deadlines and alerts](deadlines-and-alerts.md).
- **Grades and scores** are tracked per course. Ask "What's my grade in physics?" or "What do I need on the final to get an A?"
- **Missing work** is flagged in the briefing, plainly.
- **New grades and instructor comments** are listed in the briefing under "From Canvas."
- **Course files** are copied into the course's `Canvas` folder, organized by module under `Canvas/Modules`, with a readable copy beside each one so Claude can search it.
- **Announcements** are saved in the course's `Announcements` folder. Recent ones, along with messages instructors send you in the Canvas inbox, are read for changes: a canceled or moved class, something to bring, something to do before class. Those changes reach your calendar and your briefing.
- **Graded work counts** toward where you stand on each topic, so exam warnings can say things like "your homework on its topics averages 64%." See [Where you stand](where-you-stand.md).

Ask Claude about any of it: "What did Dr. Lee say about my lab report?" or "Anything missing in chemistry?"

## Getting the most out of it

- **Sign in, don't stop at the feed.** The calendar feed only has due dates. Grades, files, announcements, and messages all need the sign-in.
- **Save your username and password in Oso.** Then, when Canvas logs you out, Oso signs back in on its own. If your school uses a two-step check like Duo, you just approve it on your phone.
- **Watch for the "sign in again" notification.** Canvas ends sign-ins every so often. Click the notification and sign in; until then, due dates keep coming from the feed.
- **Ask about comments.** Instructors often leave feedback you'd otherwise never open. Ask Claude what they said and what to fix.
- **Let it read your files.** Slides and handouts posted in Canvas are searchable alongside your own notes, so "explain this from the lecture slides" just works.

## Setting it up

You add the calendar feed when you install Oso. The sign-in is a separate step: in your command window run `oso connect-canvas`, or click **Sign in to Canvas** in the Oso window. A small window opens your school's Canvas sign-in page; sign in as usual and it closes itself. See [Install guide: Canvas sign-in](../install.md#canvas-sign-in).

If your school allows Canvas access tokens, you can use one instead of signing in. The install guide covers that too.

## Good to know

- **Oso only reads.** It never submits, posts, or changes anything in Canvas. Messages from instructors stay unread in Canvas, so you'll still see them there.
- **Only recent announcements and messages are read for changes** (about the last three days). Older ones are history, not news.
- **Your username and password** are kept in your computer's credential store, never in a file.
- **Canvas's notification emails are set aside** without being read, because Oso reads the same things from Canvas directly.
- `oso canvas --raw` shows everything Oso has read from Canvas. `oso disconnect-canvas` makes it forget the sign-in.
- If the sign-in stops working or the feed is rejected, see [Troubleshooting](../troubleshooting.md).
