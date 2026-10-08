# Studying

Ask Claude anything about your classes and it answers from your own notes, your textbooks, and your course materials, and tells you which page or note each answer came from. It can also explain topics, summarize, write study guides, quiz you, check your work, make flashcards, and plan your study time.

## What it's for

General AI answers sound right but don't match your class: different notation, different methods, topics your instructor never covered. Oso keeps Claude tied to your course. The textbook is the authority, your notes come next, and anything from outside them is labeled as such. Everything is also aimed at where you actually stand, so practice goes to your weak topics instead of the ones you already know.

## How to use it

Start a chat in the Oso project and ask in plain words. Or type `/` to see the commands.

- **Explain**: "Explain the chain rule from my notes." Claude explains it from your book and notes, in your course's notation. If your notes disagree with the book (a wrong sign, a formula that's off), it tells you and goes with the book.
- **Summarize**: "Summarize Tuesday's physics notes in three sentences." It gives you three sentences. With no length, you get a short paragraph.
- **Study guide**: "Make a study guide for the physics midterm." You get one section per topic the exam covers, with key ideas, formulas, and problem types. Your weak topics get more depth and a "watch out" for mistakes you've been making. Gaps where your notes are thin are listed, never filled in with made-up content.
- **Quiz or practice test**: "Quiz me on chapter 3" or "give me a practice test for Exam 2." The quiz opens in a window on your computer, one timed question at a time, with the answers hidden until you submit. Multiple choice is graded right away. For worked problems, write each answer on paper on a page labeled with the question number in the top corner, then add the pages when the window asks by picking a scan or photo (or pulling them from a plugged-in reMarkable, if you use one). Tell Claude you're done and it grades the rest. `oso quiz` reopens a quiz you closed before submitting.
- **Check your work**: "Here's my attempt at problem 4, where did I go wrong?" Attach a photo if it's on paper. Claude finds the first mistake, names it, and gives you a hint for the next step, not the answer. You get the full solution if you ask again or say you're done trying.
- **Flashcards**: "Make flashcards for the vocabulary in lecture 5." Cards are saved in the course's `Notes` folder for the Spaced Repetition plugin in Obsidian. This is the one thing Claude always saves as a file.
- **Study plan**: "Plan my studying for next week and put it on my calendar." Claude works back from your exams and deadlines, avoids your classes and other plans, and splits time by what needs it most. It shows you the plan first and asks before putting the blocks on the Oso calendar.
- **Check your notes against the book**: "Check my notes from Monday's lecture against the textbook." You get three short lists: what's wrong, what's missing, and what the book covers that your notes skip. Corrections are saved beside your note only if you say yes, never inside it.

## Getting the most out of it

- Quiz yourself instead of rereading. Results are what move a topic forward in [where you stand](where-you-stand.md); reading and explanations don't.
- Before an exam, ask for a study guide first, then a practice test on the same exam. Both aim at your weak topics.
- Try the problem before asking Claude to check it. A hint after a real attempt teaches more than a worked answer.
- Ask "where did that come from?" when something looks off. Every answer can point to its page or note.
- Keep one chat per subject or task, and start a new one when you switch. See [Getting the Most Out of Oso](../getting-the-most-out-of-oso.md).
- If you prefer a certain kind of explanation (worked examples, analogies, shorter answers), say so once. Claude remembers how you learn best.

## Setting it up

Your courses need to be set up first, so Claude knows each syllabus, topic list, and exam: see [Install guide: Set up your courses](../install.md#set-up-your-courses). Textbooks make answers much better: see [Textbooks](textbooks.md). For flashcards, install the Spaced Repetition plugin in Obsidian ([Install guide: Accounts and apps](../install.md#accounts-and-apps)).

## Good to know

- Claude teaches and checks your work. It never writes answers you could hand in for a grade.
- Each course's AI policy is saved from its syllabus. Claude mentions it only when it forbids what you asked.
- When your notes and book have nothing on a question, Claude says so and marks any general explanation as coming from outside them.
- Answers stay in the chat at the length you ask for. Claude saves a file only when you ask, except flashcards.
- Study guides and practice tests use a stronger model than everyday answers. You can change it in the Oso window's Settings tab.
