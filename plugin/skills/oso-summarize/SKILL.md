---
name: oso-summarize
description: Summarize a lecture, chapter, reading, or a set of notes from the vault. Use when asked to summarize, recap, or give the key points of course material.
---

# Summarize course material

1. Find the material: search the course folder (`Courses/<folder>/`) with your file search by name or topic, then `read_note` on the path (it comes back in pieces if long; keep calling with `next_start`). State the course's `ai_policy` in one line.
2. Read the whole thing before writing.
3. Write the summary and save it next to the source as `<source name> summary.md` with front matter (`type: summary`, `course`, `source: [[path]]`, `generated`):
   - **In one sentence**: what this material is about.
   - **Key ideas**: five to ten bullets in the order presented, each a complete thought, with definitions and formulas in place.
   - **Worked examples**: one line each, what the example showed.
   - **Connections**: how this relates to earlier material in the vault, with `[[path]]` citations.
   - **Likely exam material**: what the instructor emphasized, if the material shows it.
4. Keep it under a fifth of the source's length. The student should be able to read it in two minutes.

Do not add content the source does not contain. If the source is a converted slide deck with little text, say the summary is thin and why.
