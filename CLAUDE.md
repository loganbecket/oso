# Oso

Oso is a study assistant for college students, built from three things: an Obsidian vault that holds everything the student reads and writes, Claude on a Pro subscription (Cowork for the student, Claude Code for installation and local runs) for intelligence, and a small Python service on the student's Windows laptop for plumbing. Oso contains no model calls of its own and runs no server. A student installs it once from this repo and owns it.

Read `docs/spec.md` for what Oso does and why, and `docs/plan.md` for what to build next.

## Rules for working in this repo

- No direct model API usage anywhere. Everything intelligent runs inside Cowork or Claude Code through the skills in `plugin/`.
- The service is plain Python with no model in the path: connectors, SQLite, change detection, file conversion, and writing generated notes into the vault.
- The vault is the source of truth for knowledge; SQLite is the source of truth for deadlines and grades. Never duplicate one into the other.
- The service writes only into `Inbox/` and generated files (`Today.md`, `Dashboard.md`). It never edits a note the student wrote.
- Read-only toward every school system. The only external write is one dedicated Google Calendar.
- Credentials live in Windows Credential Manager. Never in files, logs, or prompts.
- Every failure the student can see must be a plain sentence, not a stack trace.
- American English spelling in code, comments, and docs.

## Layout

- `service/` Python service and connectors
- `plugin/` Claude plugin: skills and MCP server configuration
- `vault-template/` starting layout for a new vault
- `docs/` spec and plan
