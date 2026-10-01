# Design notes

**English** | [简体中文](DESIGN.zh-CN.md)

Notes for my future self on why things are the way they are.

## In one sentence

**A to-do list plus an alarm clock, all local.**

Version 0.1 used Claude to break plans into tasks, tracked focus time from keyboard / mouse
activity, and had a rules engine decide when to nag. In practice only two things got used every
day: writing down what to do, and being told to take a break. 0.2 deleted everything else.

## Layers

```
ui/          ← Qt; the only layer that knows there is a UI
  ↓ calls
core/        ← domain models + SQLite
reminder.py  ← background PowerShell process (no Qt, testable)
i18n.py      ← 中文 / English (no Qt)
config.py    ← every tunable
```

## Why completion is stored per *period*

Daily / weekly / yearly tasks recur. The obvious design is a `done` flag reset at midnight, but
that assumes something is running at midnight. Leave the PC off overnight and the reset is
missed, so you need catch-up logic.

Instead: `todo_done(todo_id, period)`, where period is `2026-09-24` / `2026-W39` / `2026`.
"Is it done?" means "is there a row for the current period?". Crossing into a new day / week /
year needs no work: reading with a new key naturally returns "not done". History comes for free.

**Daily tasks are the exception: their period is a *round*, not a date.** It turned out a "day"
shouldn't be defined by the calendar. If you're still up past midnight, it's still "today" for
you. So daily tasks never reset on their own. The current round's key lives in
`meta.daily_round`, and **New round** switches to a new key (`round-<counter>`; not a timestamp,
because Windows clock resolution is coarse enough that a double-click could produce the same key
twice). When upgrading from the date-based version, the first round's key is today's date, so
whatever you already checked today still counts. Daily rewards follow the round with the same
mechanism and no extra code.

Today tasks are one-offs; their period is fixed to their own day. If you check one off days later,
the row still belongs to that day. It disappears once checked and doesn't come back when "today"
moves on.

Weeks are ISO weeks (starting Monday). Around New Year, `isocalendar()` puts e.g. Dec 29 into
week 1 of the next year, which is right: that week is a single week.

## Why the reminder is a PowerShell child process, not a Qt timer

The feature request came as a PowerShell command. `System.Speech` works out of the box in
Windows PowerShell 5.1, so Python doesn't need a TTS library, and `MessageBox` comes with it too.

The price is managing that process's lifetime:

- **No `Start-Process`.** We `Popen` it ourselves and keep the handle.
- **Job Object + `KILL_ON_JOB_CLOSE`.** `quit()` terminates it explicitly, but when the app
  crashes or is ended from Task Manager, Python gets no chance to clean up. The job handle is a
  kernel object: when our process dies Windows closes it, and everything in the job is killed.
  `tests/test_reminder.py::test_child_dies_when_parent_is_killed` hard-kills the parent with
  TerminateProcess to prove it.
- **`-EncodedCommand`.** The script is passed as UTF-16LE base64, so Chinese text, quotes and `$`
  need no escaping and the console code page doesn't matter (0.1 got bitten by this once).
- **Errors go to stdout; stderr is discarded.** With stdout redirected, PowerShell writes
  CLIXML to stderr (including module-loading progress bars), which no human can read. A `trap` in
  the script prints the exception as a single `ERROR: ...` line, with `[Console]::OutputEncoding`
  set to UTF-8, so the app can show it verbatim.
- **"It's running" needs evidence.** After loading assemblies and picking a voice, the script
  prints a ready marker that includes the chosen voice and its culture. Only then does the app
  say "running", and it warns if the voice doesn't match the UI language. If the process exits,
  the app shows the exit code and the last lines of the log.

The popup blocking the loop is deliberate: the next hour starts after you dismiss it. If you're
away, you don't come back to a pile of boxes.

## Rewards: record that it was paid out

`reward_claims(reward_id, period)` follows the same idea as completion: insert a row when the
threshold is reached; "earned this period?" means "is there a row?". So:

- Unchecking and re-checking doesn't pay twice. We check "was it paid?", not "did we just cross?".
- A new period starts fresh with nothing to reset.
- Percentages compare integers (`done * 100 >= percent * total`), so 1 of 3 is reliably ≥ 33%,
  with no floating-point edge cases.

The check runs only on a check-off and when the Rewards window closes, not in the timer loop.
A reward is a response to an action; popping up minutes later loses the point.

## Activity graph: a separate append-only table

Drawing straight from `todo_done` would be easiest, but those rows are deleted along with their
task (foreign-key cascade): delete a daily task and its whole year of squares disappears. So there
is a separate `activity` table. Each check-off appends a row with **a copy of the title**, with no
foreign key, so deleting tasks or rewards leaves it untouched.

Unchecking is the only operation that removes a row, because it means the check was a mistake.
It removes the matching `(task, period)` entry.

The day is the date of the moment it was done (the first 10 characters of `at`), not the period.
A daily task checked after midnight lands on the new day, because that's what actually happened.

Grid layout, shading and streaks live in `core/stats.py` as pure functions; the tests don't need Qt.

## 中文 / English: the Chinese text is the key

`t("完成 {done}/{total}", done=1, total=3)`: the Chinese source string is the key, looked up in
`i18n.EN` in English mode. We don't use Qt's `.ts/.qm` workflow, which needs the lupdate / lrelease
toolchain and an extra compile step. For an app this size a dict is enough, and the code still
reads the way it did.

The downside is that a missing translation doesn't fail loudly; it just shows Chinese in the
English UI. So `tests/test_i18n.py` walks the AST for every `t("...")` call (including strings
concatenated across lines) and fails on a missing translation, mismatched `{placeholders}`, or a
stale entry in the English table that nothing uses any more.

Switching is **live**: the main and activity windows are rebuilt in the new language (keeping
their position and any half-typed task), the tray menu is rebuilt, Qt's own translation for
dialog buttons is installed or removed, and the reminder restarts with the new language's text
and voice. We rebuild rather than calling `retranslate` on each widget, because most text is
assembled during `refresh()`; patching it piece by piece would be more code and easier to get wrong.

Default reminder text follows the language: if the configured value equals the default of *any*
language, it's treated as "not customised" and the current language's default is used; anything
else is used as-is. That keeps existing configs (which store the Chinese defaults) correct in English.

## Packaging: PyInstaller one-folder + Inno Setup

- **Not a one-file exe.** One-file builds unpack to a temp folder on every start, which is slow
  and often flagged by antivirus. One-folder, installed under `%LOCALAPPDATA%\Programs\jo-app`,
  just runs.
- **No admin rights** (`PrivilegesRequired=lowest`). Start-with-Windows writes the HKCU Run key.
- **Installing / uninstalling while it runs:** a running exe can't be overwritten. The app
  creates a named mutex `jo-app-running`, and the installer's `AppMutex` asks the user to quit first.
- **Drop the Qt files we don't use** (in `build.ps1`): software OpenGL, QML, PDF, virtual
  keyboard. 120 MB → 76 MB. With the plugins gone, Qt never tries to load them.
- **CI and local builds use the same script.** CI installs a pinned Inno Setup (7.1.0), which
  ships the Simplified Chinese messages; the installer is English + Chinese, picked from Windows.

## Why quitting uses exit(), not quit()

In Qt 6, `QCoreApplication::quit()` is only a **request**: it first asks each top-level window
whether it may close, and gives up if any says no. Our main window always says no, because
× means "hide to tray". The result: **Quit** sometimes did nothing (depending on window state and
timing; about half the time in tests).

Now a real quit first sets `allow_close` on the main window, closes the windows itself, and ends
the event loop with `exit(0)`. When Windows asks during shutdown / logoff (`commitDataRequest`),
closing is allowed as well.

## Pin on top: Qt's flag, not SetWindowPos

The 📌 uses `Qt.WindowStaysOnTopHint` rather than calling `SetWindowPos(HWND_TOPMOST)` directly.
In testing, a topmost state set behind Qt's back didn't stick: Qt manages the window's Z-order
itself and wins. With Qt's flag, the window stays on top through raise / activate / hide-and-show,
and dialogs opened from it (delete confirmation, rewards) are on top too. Changing the flag makes
Qt hide the window for a moment (same native handle), so it's shown again immediately.
At startup the flag is set before the first show, so there's no flash.

## Why closing the window doesn't quit

The reminder should run while you work, and you don't keep the list open while you work. So ×
only hides to the tray; the Quit button and the tray's Quit really exit and stop the reminder.
The first time the window hides, a notification explains this.

Double-clicking the shortcut again makes the second instance ask the first (via `QLocalServer`)
to show its window, then exit. Otherwise the single-instance lock would make the double-click
appear to do nothing, which looks broken.

## Why SQLite, not a JSON file

- Completion history only grows; appending is safer than rewriting a whole file.
- If you want to query your data yourself, SQLite has the tooling.
- It's in the standard library, zero dependencies.

## Known rough edges

- Reminder text can only be changed in `config.json`, and needs a restart.
- Tasks can't be renamed or reordered. Delete and re-add to rename.
- The reminder doesn't know whether you're at the PC. Walk away for two hours and you come back
  to one popup (only one).
