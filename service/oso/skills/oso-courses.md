# Manage courses

1. Call `list_courses` to see each course's term, whether it is finished, and what it is related to.
2. Do what the student asked:
   - **Finish a course** when its semester is over (the student says so, or `Today.md` suggests it): `update_course` with `finished` true. Its deadlines, alerts, and dashboard row disappear, and default searches skip it. Its notes stay where they are and can still be searched by naming the course.
   - **Make a course current again**: `update_course` with `finished` false.
   - **Follow an instructor's website**: when the student says an instructor posts materials on a site, `update_course` with `add_site` and the address. Oso checks it a few times a day, saves new and changed pages and the documents they link to into the course's `Web` folder, and lists what's new in the briefing. `remove_site` stops following one. Sites that need a sign-in can't be followed; say so if the student mentions one.
   - **Relate courses**: `update_course` with `related` set to the earlier courses a course builds on (codes or names). Searches in that course then include their notes. This replaces the list, so include any that are already there.
3. Reply in one line with what changed.

Never move or rename a course folder; links between notes depend on it.
