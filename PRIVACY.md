# Oso privacy policy

Oso is a program that runs entirely on the user's own computer. It has no server, and its developer receives no data from it.

## Google Calendar

When the user connects Google Calendar, Oso asks for permission to create calendars and manage the events on calendars it created (`calendar.app.created`). It uses that permission only to:

- create one calendar named "Oso" in the user's Google account, and
- add events to that calendar for changes to the user's coursework, such as a moved due date.

Oso cannot see or change any other calendar. The sign-in token is stored in the operating system's credential store on the user's computer and is never sent anywhere except to Google. The user can revoke access at any time with `oso disconnect-calendar` or at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## Other data

Course information Oso collects, such as deadlines from Canvas and notes from a reMarkable tablet, is stored on the user's computer and in the user's own Google Drive. It is not shared with the developer or any third party by Oso.

## Contact

Questions about this policy: open an issue at [github.com/loganbecket/oso](https://github.com/loganbecket/oso/issues).
