# Commands

You rarely need these: the Oso window and the Claude app do the same things. They're here for reference, and for when the Claude app can't reach Oso. Type them in a command window ([how to open one](install.md#a-command-window)).

## Everyday

```
oso sync                  check every source now and rewrite Today.md and Dashboard.md
oso settings              open the Oso window (status, settings, and actions)
oso doctor [--fix]        check the installation and explain anything wrong
oso health                when each source last synced
oso transcribe            turn queued handwritten pages into notes
oso quiz [N]              reopen a quiz window (the latest one not yet submitted)
oso update                install the newest Oso on your update channel
oso update --version V    install an exact earlier version
oso backup                back up now (--set-folder PATH sets the backup folder)
```

## Connections

```
oso connect-canvas        sign in to Canvas so Oso can read grades and coursework
oso disconnect-canvas     forget the Canvas sign-in
oso connect-calendar      let Oso keep its own Google calendar (--client-file FILE the first time)
oso disconnect-calendar   stop that and forget the access
oso connect-email         let Oso read the Gmail your school email is forwarded to, and send your feedback
oso disconnect-email      stop reading email and forget its access
oso connect-groupme       let Oso read your GroupMe groups
oso disconnect-groupme    stop reading GroupMe and forget the token
oso connect-tasks         keep your tasks in a Google Tasks list named Oso
oso disconnect-tasks      stop using Google Tasks and forget its access
```

## Courses and materials

```
oso add-course            register a course by hand (usually /create-course in Claude does this)
oso set-drive-folder      mirror a shared Google Drive folder into a course
oso set-remarkable-folder the tablet folder that holds the course folders
oso books                 how far Oso has read each textbook (--reprocess TITLE reads one again)
oso sites                 instructor websites Oso follows (--add COURSE URL, --check)
oso canvas --raw          show what Oso has read from Canvas
oso profile --raw         show every recorded quiz, question by question (--delete-quiz N removes one)
```

## Setup and starting over

```
oso init                  point Oso at your vault and Canvas calendar feed
oso install-task          schedule the automatic check (every 15 minutes by default)
oso watch                 take in new files as they arrive (runs on its own from sign-in)
oso reset-skills [NAME]   put back Oso's version of its commands (all, or the ones named)
oso restore --from PATH   bring the vault and Oso's records back from a backup
oso fresh-start           start over as if newly installed, keeping your settings (deletes the vault's contents)
```
