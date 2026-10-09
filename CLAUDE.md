# Oso

Oso is a study assistant for college students, built from three things: an Obsidian vault that holds everything the student reads and writes, Claude on a Pro subscription (Cowork for the student, Claude Code for installation and local runs) for intelligence, and a small Python service on the student's computer (Windows, macOS, or Linux) for plumbing. Oso contains no model calls of its own and runs no server. A student installs it once from this repo and owns it.

Read `docs/spec.md` for what Oso does and why.

## Rules for working in this repo

- No direct model API usage anywhere. Everything intelligent runs inside Cowork or Claude Code through the skills in `plugin/`.
- The service is plain Python with no generative model in the path: connectors, SQLite, change detection, file conversion, search, and writing generated notes into the vault. The one model it runs is the small local embedding model behind search (`search.py`), which Oso downloads itself; nothing for the student to install.
- The vault is the source of truth for knowledge; SQLite is the source of truth for deadlines and grades. The search index is a disposable copy of the vault, rebuilt from it on every sync.
- The service writes only into `Oso/`, generated files (`Today.md`, `Dashboard.md`), and the course folders it fills (Canvas, Drive, Handwriting, filed clippings, and the chapter notes it writes from the books in `Books`). In `Oso/Skills/` it replaces a command's instructions only when the student has not edited them (`skillsync.py`). It never edits a note the student wrote.
- Skill instructions live in `service/oso/skills/`; each plugin skill is a one-line pointer to them. Edit the instructions there, not in `plugin/`.
- Read-only toward every school system.
- Credentials live in the operating system's credential store. Never in files, logs, or prompts.
- Every failure the student can see must be a plain sentence, not a stack trace.
- Every new or changed feature is documented in the same change: a one-line entry in the README's feature list and its own page in `docs/features/` (what it is, what it's for, how to use it, getting the most out of it), plus the install guide when it needs setup.
- American English spelling in code, comments, and docs.
- master must always install and run: it is what the latest channel ships, and stable is the highest `vX.Y.Z` tag.

## Layout

- `service/` Python service and connectors
- `plugin/` Claude plugin: skills and MCP server configuration
- `install.ps1`, `install.sh` installers that download from GitHub (no Git needed)
- `obsidian/` the Web Clipper template
- `docs/` spec, install guide, troubleshooting, commands, and one page per feature in `docs/features/`
