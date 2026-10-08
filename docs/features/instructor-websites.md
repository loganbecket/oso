# Instructors' websites

Some instructors post slides, homework, and notes on their own website instead of Canvas. Oso can follow those sites and bring new material into your course folder on its own.

## What it's for

A professor's personal page is easy to forget about. Homework gets posted there on a Tuesday night and you don't find out until class. When Oso follows the site, new and changed pages and documents land in your vault, become searchable like anything else, and show up in your briefing.

## How to use it

Tell Claude where the instructor posts things:

- "Dr. Lee posts physics materials at https://physics.example.edu/~lee/phys110"
- "Stop following Dr. Lee's site."

Course setup also asks about any website the syllabus mentions.

After that, a few times a day Oso visits the page and the pages it links to, and:

- saves a readable copy of each page in the course's `Web` folder, updated only when the page changes
- downloads the documents those pages link to (PDF, Word, PowerPoint, Excel, text) into the same folder, where they're converted and searchable
- lists what's new in your briefing: "Physics: Dr. Lee's site has a new file, HW 6.pdf"

Then just ask: "What's on the new physics homework?" or "Summarize this week's slides from Dr. Lee's site."

## Getting the most out of it

- **Give the page where materials are listed,** like the course schedule or homework page, not the instructor's home page.
- **Add every site you use.** Some instructors have one page for slides and another for homework. Name each one.
- **Mention it during course setup** so it's followed from day one.
- **Check the briefing.** It's how you'll find out a new assignment was posted without visiting the site.

## Good to know

- **Sites that need a sign-in can't be followed.** Oso tells you so instead of saving an empty page. The same goes for pages that only show their content when run in a browser.
- **It's polite.** Oso respects what the site allows, asks whether anything changed before downloading again, and waits between requests.
- **No Claude usage.** Following sites is done by Oso alone.
- `oso sites` lists what's followed; `oso sites --check` checks now.
