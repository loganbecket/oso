# Getting the Most Out of Oso

## How it fits together

The Oso project in Cowork is your home base: ask it anything about your classes and it answers from your own notes, Canvas, and email.

- **Always start chats inside the Oso project.** That's where Oso's tools and your course materials are hooked up. A chat outside it is plain Claude and knows nothing about your classes.
- **Oso keeps itself up to date in the background.** Deadlines, grades, Canvas changes, and new materials sync on their own. You don't need to tell it to check.
- **It works from your phone too.** Same project in the Claude app, and voice mode works for quick questions while walking to class.
- **Ask for sources.** Answers come with a citation to the note or page they came from. If something looks off, ask where it came from.

## Keep conversations short and on one topic

The single biggest habit: one chat per task, and a fresh chat when you switch subjects.

- **Every message makes Claude reread the whole chat.** A long chat gets slower, gets fuzzier about details from early on, and burns through your Pro usage limit much faster.
- **Start a new chat when you change subjects.** Done with chem homework and moving to calc? New chat. Studying for a new exam? New chat.
- **Long chats get condensed automatically.** When a chat gets very long, Claude shrinks the older parts into a summary so it can keep going. That works, but small details can get lost along the way.
- **To carry work into a fresh chat,** ask: "Summarize where we are so I can pick this up in a new chat." Paste that summary as the first message of the new one.
- **You don't lose anything by starting over.** Your notes, grades, deadlines, and rules all live in Oso, not in the chat. A brand-new chat knows all of it.

## Oso's commands

Type `/` in the message box to see every Oso command, or just ask in plain English and Oso picks the right one.

| Command | Use it when |
| --- | --- |
| `/oso-briefing` | You want to know what's due and what to do today |
| `/oso-explain` | You're stuck on a concept: "what is," "how do I," "why does" |
| `/oso-check` | You want your own work checked (a photo is fine). It shows where it went wrong and teaches the method |
| `/oso-quiz` | You want practice questions or a practice test before an exam |
| `/oso-study-guide` | An exam is coming and you want a review sheet scoped to what it covers |
| `/oso-plan` | You want study time scheduled on your calendar, working back from exam dates |
| `/oso-summarize` | You want the key points of a lecture, chapter, or reading |
| `/oso-flashcards` | You need to memorize terms, formulas, or definitions |
| `/oso-check-notes` | You want your notes compared against the textbook for mistakes and gaps |
| `/oso-grades` | You want to know where you stand, or what you need on the final |
| `/oso-profile` | You want to know what you're strong and weak at in a course |
| `/create-course` | You're adding a new class (have the syllabus handy) |
| `/oso-rules` | You want Oso to do something a certain way from now on |
| `/oso-tasks` | You want to add, see, or check off things to get done, or be reminded of something after class |
| `/oso-feedback` | Something in Oso is broken, confusing, or you have an idea |
| `/oso-doctor` | Something seems off: the briefing is missing, deadlines look stale, or you want Oso's settings |

Oso tutors; it won't write answers for you to hand in. If a class's AI policy forbids what you asked, it will tell you.

## Studying for an exam

Start two to three weeks out and use Oso's study tools in this order. Each step tells Oso more about what you know, so the next one is aimed better.

1. **After every lecture: check your notes.** Run `/oso-check-notes` on that day's notes. It compares them to the textbook and lists anything wrong, anything missing, and book sections the lecture skipped that you still need to read. Catching a wrong formula in week 3 beats finding it on the exam.
2. **Two to three weeks out: make a plan.** Ask `/oso-plan` to plan your studying. It works back from the exam date, spreads sessions over several days with review at the end, and can put them on your calendar. Tell it which hours you're actually free.
3. **Early in your studying: get a study guide.** Ask `/oso-study-guide` and name the exam. It covers only what the exam covers and spends the most space on your weak topics. Pay attention to the "gaps" list at the end: those are assigned chapters where your notes are thin, so read them in the book.
4. **All the way through: quiz yourself, more than once.** Ask `/oso-quiz` and name the exam or a topic. If you don't name one, Oso aims at your weak spots. It gives 5 questions by default; ask for more, or for a full practice exam.
5. **For anything you have to memorize: flashcards.** Ask `/oso-flashcards` for a chapter, lecture, or topic. Oso makes cards for definitions, formulas, and common traps, leaning toward your weak topics, and saves them in Obsidian for you to review there. A few minutes a day beats one long cram session.
6. **Final few days: fresh questions, not repeats.** In the Quizzes tab of the Oso window, take a new version of an earlier quiz rather than a retake. A retake reuses questions you've already seen, so getting them right doesn't count as progress.

How quizzes work:

- **They open in the Oso window on your computer, not in the chat.** On your phone, ask for the quiz in the chat instead.
- **Do worked problems on paper.** Write the question number in the top corner of each page, add photos of the pages when the window asks, then go back to the chat and say you're done. Oso grades it there.
- **Read the feedback on what you got wrong.** It explains each mistake and the right method, with the textbook page. To go over an old one later, ask something like "show me my last physics quiz."
- **Expect honest grading.** If you think a grade is wrong, say why and Oso will look again, but it changes the grade only if your answer actually meets the grading criteria.

## Teach it what you want

If you find yourself repeating the same request, turn it into a rule so you never have to say it again.

- **Say "from now on..."** and Oso saves it as a rule that every future chat follows. Examples: "From now on, keep the briefing to five lines." "Every time a new exam shows up, put study blocks on my calendar." "Always quiz me with problems, not definitions."
- **Rules are Oso's long-term memory.** A chat forgets everything when it ends; a rule doesn't. Ask "what rules do I have?" to see them, or say "stop doing that" to change or delete one.
- **Correct it when it's wrong.** If a quiz grade or a weak-topic rating got recorded wrong, say so and it will fix it. Your profile only helps if it's accurate.
- **Use `/oso-feedback` for anything about Oso itself.** Bugs, confusing behavior, and ideas go straight to whoever builds Oso, and the briefing tells you when your fix or idea has shipped.

## Using AI wisely

Claude is a powerful tool, but it isn't always right, and it's not a substitute for your own work.

- **It can be confidently wrong.** Before you rely on an important date, formula, or fact, check the note or page it cites.
- **Every class has its own AI rules.** Using Oso to learn is fine almost everywhere, but turning in anything it wrote usually isn't. Know each class's policy.
- **Keep passwords and other people's private information out of chats.**

## Long-term upkeep

There isn't much to maintain, but a few habits keep Oso working well from one semester to the next.

- **No need to delete old chats.** Each new chat starts fresh, so old ones don't slow anything down or change Oso's answers. Delete them only if you want them gone for privacy.
- **Close out each semester.** When finals are over, tell Oso your courses are finished. That takes them out of the briefing and study plans, and your notes stay available for later classes that build on them.
- **Review your rules now and then.** Ask "what rules do I have?" and delete any you no longer want. Old rules keep shaping every chat until you remove them.

## Habits that pay off

- **Read the briefing every morning.** It leads with anything that changes class today.
- **Do your homework yourself first, then have Oso check it.** When you're stuck on a homework or practice problem, don't ask for the answer. Work it as far as you can, then send a photo of your work with `/oso-check`. It finds where you went wrong and teaches you that step, which sticks far better than being handed the answer.
- **Quiz yourself before every exam,** not just study guides. Your quiz results tell Oso what to focus on next time.
- **Be specific.** "Explain chapter 4" gets a so-so answer; "I don't get why the integral flips sign in problem 12" gets a great one.
- **Push back.** If an answer is too long, too vague, or wrong, say so. Claude adjusts right away, and if you want it permanent, make it a rule.
