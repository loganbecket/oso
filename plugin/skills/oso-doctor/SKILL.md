---
name: oso-doctor
description: Check whether Oso is working and fix common problems. Use when the briefing is missing, deadlines look stale, a connection shows as failing, or the student asks whether Oso is set up right. Runs in Claude Code on the laptop.
---

# Is Oso healthy?

1. Run `oso doctor --fix` in the terminal and read every line.
2. For each WARN or FAIL, do the obvious fix if it is safe and local:
   - missing folders: already fixed by `--fix`
   - no sync yet or Today.md missing: run `oso sync`
   - scheduled task or timer missing: run `oso install-task`
   - `oso-mcp` not on PATH: run `uv tool install --force <repo path>` and restart Cowork or Claude Code
   - a source that has never succeeded: read the error. If it says the login was rejected or the address no longer works, the student needs to copy a fresh Calendar Feed URL from Canvas (Calendar, then Calendar Feed) and run `oso init` again with it. Do not guess at URLs or tokens.
3. Run `oso doctor` again and show the result.
4. Explain anything still wrong in one or two plain sentences, with the exact command the student should run.

Never edit the config file by hand; use the `oso` commands. Never print or ask for the feed URL or token in chat if it can be avoided.
