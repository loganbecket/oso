---
name: oso-flashcards
description: Make flashcards from course notes for spaced repetition in Obsidian. Use when asked for flashcards, review cards, or to memorize terms, formulas, or definitions.
---

# Flashcards

1. Settle the scope (a lecture, a topic, an exam) and state the course's `ai_policy` in one line.
2. `search_notes` and open the sources. Cards come only from the materials.
3. Write to `Courses/<folder>/Notes/Flashcards <scope>.md` with front matter `type: flashcards`, `course`, `scope`, `generated`, using the format the Obsidian Spaced Repetition plugin reads:

   ```
   #flashcards/<course folder>

   What is the derivative of sin(x)?
   ?
   cos(x)

   The chain rule states that::$\frac{d}{dx} f(g(x)) = f'(g(x)) g'(x)$
   ```

   One blank line between cards. Use `?` for question-and-answer cards and `::` for one-line definition cards.
4. Aim for 15 to 40 cards: definitions, formulas with every symbol named, the conditions under which a method applies, and the common mistakes the notes call out. Each card tests one thing.
5. Prefer topics that appear in `Courses/<folder>/Notes/Practice log.md` as weak.
6. Tell the student the file name and that the Spaced Repetition plugin will pick it up; offer to install it if they have not.

Never invent a fact for a card. If the notes are thin, make fewer cards and say so.
