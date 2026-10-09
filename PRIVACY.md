# Oso privacy policy

Oso runs on the user's own computer. It has no server of its own. This page lists everything it sends off the computer, and to whom.

## What leaves the computer, and where it goes

- **Google** (Calendar, Gmail, Tasks, Drive), only after the user connects each one:
  - Calendar: permission to create calendars and manage events on calendars it created (`calendar.app.created`). Oso creates one calendar named "Oso" and puts coursework changes, class meetings, and study blocks on it. It cannot see or change any other calendar.
  - Gmail: permission to read mail (`gmail.readonly`) so new school email can be read, and to send mail (`gmail.send`) for one purpose: feedback about Oso that the user asks to pass on, sent to the person who builds Oso. Nothing else is ever sent, and no email is ever changed, moved, or marked read.
  - Tasks: the user's task lists, read and written, so Oso's task list and Google Tasks stay the same.
  - Drive is used only through Google Drive for Desktop, which the user sets up; Oso itself never calls Drive.
- **Anthropic**, through the user's own Claude subscription. Course content, notes, handwriting images, school email, and GroupMe messages reach Anthropic when the user asks Claude something with Oso connected, and also in the background: Oso runs Claude Code on the computer to read handwritten pages and scanned textbook pages, to read new school email and GroupMe messages for deadlines and events, and to act on rules the user set. All of that is under the consumer terms of the user's Claude subscription.
- **The user's school**, read-only: Canvas (through the calendar feed, an access token, or the user's own browser sign-in) is only ever read. Oso writes nothing to any school system.
- **GroupMe**, only if connected, read-only.
- **GitHub**: once a day Oso asks github.com whether a newer version exists, and downloads new versions from there when the user updates. The installer also downloads the `uv` installer from astral.sh.
- **Hugging Face**: on first run Oso downloads a small text-search model (`BAAI/bge-small-en-v1.5`) from huggingface.co so search can match by meaning. Nothing is sent to it afterward; search runs on the computer.
- **The person who builds Oso** receives nothing automatically. The one exception is feedback the user explicitly asks Claude to pass on, which goes by email from the user's own Gmail account and contains the user's words, what they were doing, and the Oso version.

## What stays on the computer

Deadlines, grades, notes, messages Oso has read, and the search index live on the user's computer (and in the user's own Google Drive and backup folder, if set up). Sign-ins and tokens live in the operating system's credential store and are sent only to the service they belong to. Logs hold no credentials and no note content. The Canvas sign-in window keeps its own browser memory on the computer so the school's sign-in and two-step service can remember the user.

The user can revoke Google access at any time with `oso disconnect-calendar`, `oso disconnect-email`, `oso disconnect-tasks`, or at [myaccount.google.com/permissions](https://myaccount.google.com/permissions), and can delete everything Oso holds with `oso fresh-start`.

## Contact

Questions about this policy: open an issue at [github.com/loganbecket/oso](https://github.com/loganbecket/oso/issues).
