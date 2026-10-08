# Making commands your own

Every Oso command, like summarize, quiz, or study guide, follows a set of written instructions. Those instructions are plain notes in your vault, and you can change them.

## What it's for

If you'd like summaries shorter, quizzes harder, or study guides laid out a different way, you can change the command itself instead of asking for it every time. Your version is the one Claude follows from then on.

For a quick preference, a [rule](rules.md) is usually easier: just say "from now on, keep summaries to five bullets." Editing a command is for bigger changes to how it works.

## How to use it

1. Open your vault in Obsidian and go to `Oso/Skills`. There's one note per command, named after it (for example `oso-summarize`).
2. Edit the note in plain words and save.
3. The next time you use that command, Claude follows your version.

## When Oso updates a command

Oso improves its commands over time. What happens depends on whether you changed yours:

- **You didn't change it:** your copy updates quietly. You don't have to do anything.
- **You changed it, and Oso's version didn't change:** your copy is kept.
- **You changed it, and Oso also has a new version:** your copy is kept, and your briefing tells you a new version is waiting. Ask Claude to "go through the Oso command updates." It shows what Oso changed and what you changed, and lets you keep yours, take Oso's, or combine the two.

## Getting the most out of it

- **Change one thing at a time** so you can tell what made the difference.
- **Write instructions the way you'd brief a person:** what to do, what to leave out, how long.
- **Combine when Oso updates,** rather than throwing away either side. Claude writes the combined version and shows it to you before saving.
- **Add your own commands.** A note you add to `Oso/Skills` yourself is never touched by Oso.

## Going back to Oso's version

- Ask Claude to "put Oso's commands back to the defaults," for all of them or just one.
- Or run `oso reset-skills` in your command window (`oso reset-skills oso-summarize` for just one).

Either way, your edits to those commands are lost, so Claude confirms first.

## Good to know

- Editing needs Obsidian on your computer. If you never open Obsidian, use [rules](rules.md) instead.
- Fresh start puts every command back to Oso's version.
