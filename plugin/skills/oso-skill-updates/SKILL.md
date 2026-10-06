---
name: oso-skill-updates
description: Resolve Oso command updates that clash with the student's own edits. Use when Today.md or the briefing says an Oso command has a new version, the student asks about Oso updates to their commands, or asks to reset Oso's commands to their defaults.
---

# Oso command updates

The instructions behind each Oso command live in the vault under `Oso/Skills/`, and the student may have edited them. When Oso ships a new version of one they edited, it waits here for a decision.

1. Call `resolve_skill` with no arguments. It lists each pending command with three texts: `yours` (the student's copy), `oso_new` (Oso's new version), and `oso_previous` (the version the student started from). If the list is empty, say there is nothing to resolve.
2. For each command, say in two or three plain sentences what Oso changed (compare `oso_previous` to `oso_new`) and what the student changed (compare `oso_previous` to `yours`). Then ask: keep yours, take Oso's, or combine them.
3. For "combine", write one version that keeps the student's changes and adds Oso's, show it, and save it only once they agree.
4. Call `resolve_skill` with the name and the choice: `mine`, `oso`, or `combined` (with the text).

To reset instead: if the student asks to put Oso's commands back to the defaults, confirm which ones (or all) and that their edits to those will be lost, then call `resolve_skill` with choice `default` and the name (no name resets all). The `oso reset-skills` command does the same from the command window.
