# jo-app

**English** | [简体中文](README.zh-CN.md)

> if you joke yourself, you are joker of course.

A Windows tray app for your to-do list, with timed break reminders.

- **Fully offline.** No cloud, no account, no network. Everything lives in one local SQLite file.
- **Adding a task is typing one line.** No time estimates, no breakdowns. Type it and press Enter.
- **Four groups in one window:** Daily / Today / Weekly / Yearly, all side by side, each collapsible.
- **Timed reminders.** While the app is open, a background process speaks
  "Time for some water. Get up and move around a bit." every hour and pops up a
  "Take a break." box. Quit the app and the reminder stops with it.
- **Rewards.** When your daily / weekly / yearly tasks reach 50%, 100% or any percentage you like,
  reward yourself. You define the reward, and it pops up the moment you cross the line.
- **Activity graph.** A GitHub-style contribution graph: one square per day, greener means more done.
  Click a day to see exactly what you finished and which rewards you earned.
- **Pin on top.** The 📌 in the top-left corner keeps the window above every other window,
  like a pinned image in Snipaste. Click again to unpin; it's remembered.
- **中文 / English.** Switch with one click in the top-right corner. It takes effect immediately,
  including the reminder's text, popup and voice.

## Download and install

**Direct download: [jo-app-setup.exe](https://github.com/Teneeduu/jo-app/releases/latest/download/jo-app-setup.exe)**
(always the latest version; older ones are under [Releases](https://github.com/Teneeduu/jo-app/releases))

Run it. **No admin rights and no Python needed.** It installs to
`%LOCALAPPDATA%\Programs\jo-app`. During setup you can choose a desktop shortcut and **Start with Windows**.

- Windows SmartScreen may say "Windows protected your PC" because the installer isn't code-signed.
  Click **More info** → **Run anyway**.
- **Upgrading:** install the new version over the old one. Tasks, rewards and settings live in
  `%APPDATA%\jo-app` and are kept. If jo-app is running, the installer asks you to quit it first
  (right-click the tray icon → Quit).
- **Uninstalling:** Settings → Apps → jo-app. The data folder `%APPDATA%\jo-app` is left in place;
  delete it by hand if you want a clean slate.
- Reminders use the voices built into Windows. If the PC has no voice for your language, the
  bottom of the window says so. Add one under Settings → Time & Language → Speech.

---

## What it looks like

```
┌──────────────────────────────────────────┐
│ 📌 jo-app     Tue, Sep 29 · Week 40 [中文] │
│ ┌──────────────────────────────────────┐ │
│ │ Add a task, press Enter              │ │
│ └──────────────────────────────────────┘ │
│ [Daily] [Today] [Weekly] [Yearly]   [Add] │
│                                          │
│ ▾ Daily  1/3 · 33%  since 9/29 08:00 [↻ New round] │
│   🎁 50% Watch an episode · 100% Nice dinner │
│   ☑ Drink 8 glasses of water           ×  │
│   ☐ Learn 20 words                     ×  │
│   ☐ Stretch before bed                 ×  │
│ ▾ Today  0/2                              │
│   ☐ Send the quarterly report  2d overdue × │
│   ☐ Call mom                           ×  │
│ ▾ Weekly  0/1                             │
│   ☐ Clean the room                     ×  │
│ ▸ Yearly  0/1           ← click to fold   │
│──────────────────────────────────────────│
│ Remind every [60 min]       [Try it] [Pause] │
│ ● Reminder running  [📅 Activity] [🎁 Rewards] [Quit] │
└──────────────────────────────────────────┘
```

## The four groups

| Group | What it is | Once checked |
|---|---|---|
| **Daily** | Things you do every day | **Not reset by the calendar.** It stays done until you press **↻ New round** |
| **Today** | One-off things, tied to the day you added them | Gone the next day once done. **Unfinished ones stay** and show "*N*d overdue" |
| **Weekly** | Once-a-week things | Done for the whole week; unchecked again next Monday |
| **Yearly** | Once-a-year things / yearly goals | Done for the whole year; unchecked again next year |

- **Add:** type in the box → pick a group (Today by default, or `Ctrl+1`–`Ctrl+4`) → Enter.
- **Delete:** the `×` at the end of a row (asks to confirm).
- **New round:** the **↻ New round** button next to the Daily heading. *You* decide when a day starts.
  Staying up past midnight doesn't wipe your progress; press it when you get up. All daily tasks
  are unchecked and daily rewards can be earned again. Today / weekly / yearly are untouched.
  The time the current round started is shown next to it.
- **Pin:** the 📌 in the top-left corner keeps the window on top of everything else (it turns
  red while pinned), handy for keeping your list in view while you work. Click it again to unpin.
  It stays pinned when hidden to the tray and reopened, across language switches and restarts.
- **Fold:** click a group heading. The folded state is remembered, **except Daily, which always
  opens expanded**, so you see your daily tasks every time you open the app.

## Rewards

Click **🎁 Rewards** at the bottom. Pick a group (Daily / Weekly / Yearly), a threshold (50% and
100% are one click, or type anything from 1 to 100), write down the reward, and add it.

- The moment a check pushes you over a threshold, a box tells you what you've earned. Cross
  several thresholds at once and you get them all.
- **Each reward is given once per period:** daily rewards again after **New round**, weekly ones
  next Monday, yearly ones next year. Unchecking and re-checking doesn't pay out twice.
- Each group heading shows its completion percentage; the line underneath lists its rewards,
  with the ones earned this period in green.
- The percentage only counts that group's tasks: "Daily 50%" looks at daily tasks only.
- Today tasks can't have rewards. They're one-offs that can slip, so a percentage doesn't mean much.
- If a new reward is already reached when you add it (say you're halfway and add a 50% reward),
  you get it as soon as you close the Rewards window.

## Activity graph

Click **📅 Activity** at the bottom (or right-click the tray icon → Activity):

```
417 things done in the past year                         [Past year]
┌─────────────────────────────────────────────────────┐  [  2026   ]
│     Oct   Nov   Dec   Jan  …   Aug   Sep            │  [  2025   ]
│ Mon ▫▪▫▫▫▫▪▫▫▫▫▫▫▫▫▫▫▫▫▫▫▫▫▫▫ … ▪▪▫▪▪▪▪▪▪■▫        │
│     ▫▫▫▫▫▫▫▪▫▫▪▪▫▫▫▫▫▫▫▫▫▫▫▫▫ … ▪▪▪■▪▪▪▪▪■□        │
│ Wed …                                               │
│ Current streak 2 days · Longest 8 days  Less ▫ ▪ ▪ ■ ■ More │
└─────────────────────────────────────────────────────┘
Today · 2 done
  22:07  ✓ [Daily] Drink 8 glasses of water
  22:07  ✓ [Daily] Learn 20 words
  22:07  🎁 Reward earned: Watch an episode (Daily)
```

- One square per day, one column per week (Monday on top). Darker means more done that day.
  Shades are 4 steps relative to the busiest day in view, like GitHub.
- Hover a square to see the count; **click** it to list everything finished that day (time and
  group) plus the rewards earned.
- Switch between **Past year** and individual years on the right.
- Streaks count back from today; any day with at least one finished task counts. Not having done
  anything *yet* today doesn't break the streak.
- **Deleting a task doesn't delete its history.** Only unchecking removes the matching entry,
  because that means the check was a mistake.
- On upgrade, earlier checks and rewards are backfilled. Tasks finished in the very first version
  (the one that talked to Claude) are imported too, tagged `[old]`.

## Language

Use the button in the top-right corner (it shows **中文** in English mode and **EN** in Chinese
mode) or the tray menu. It switches **immediately**, no restart needed:

- UI text, date format ("Tue, Sep 29" ↔ "9月29日 周二") and the Yes / No buttons of dialogs.
- The reminder switches too: spoken text, popup text and title, and **which voice** is used
  (an English voice such as Zira, or a Chinese one such as Huihui). If you've written your own
  reminder text in `config.json`, it's used as-is.
- On first run it follows the Windows display language; after you switch once, your choice sticks.
- The installer is bilingual as well and picks the language from Windows.

## Opening and closing

- **Open the app:** the window pops up and the reminder starts in the background.
- **Double-click the shortcut while it's already running:** the existing window comes to the
  front (no second copy).
- **× in the window corner:** the window hides to the tray. **Reminders keep running.** Click the
  tray icon to bring it back.
- **Quit button / tray → Quit:** the app exits and **the background reminder stops with it.**

## Timed reminders

Started automatically with the app. It's roughly these two PowerShell snippets combined:

```powershell
# Speak every hour
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
while ($true) { Start-Sleep -Seconds 3600; $s.Speak("Time for some water. Get up and move around a bit.") }

# Pop up a box
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show("Take a break.", "Reminder")
```

When it fires, it speaks **and** shows the box at the same time. The box stays on top of other
windows. The next hour only starts counting after you dismiss the box, so if you're away you come
back to one box, not a pile of them.

How it differs from just running `Start-Process powershell -WindowStyle Hidden ...`:

- **It always stops when the app stops.** A `Start-Process` child is detached from the app and
  keeps talking every hour after you quit; you'd have to hunt it down in Task Manager. Here the
  reminder process is attached to a Windows Job Object, so Windows kills it whether the app
  **quits normally, crashes, or is ended from Task Manager.**
- **It picks a voice in the right language.** The default Windows voice may not match, and an
  English voice reading Chinese (or the other way round) is unintelligible.
- **You can see whether it's running.** The bottom of the window shows a green
  "● Reminder running", or a red "✕ Reminder failed to start: …" with PowerShell's own error
  message, plus a tray notification.
- **Try it:** speaks and pops up once right away, so you can check sound and popup.

Change the interval at the bottom of the window (it restarts counting from now). **Pause** /
**Resume** toggles the reminder. Both are remembered.

## Running from source

If you just want to use it, see **Download and install** above. Running from source needs Python 3.10+.

```powershell
git clone https://github.com/Teneeduu/jo-app.git
cd jo-app

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m joapp
```

### Desktop shortcut

From source there's no standalone exe. It runs on `pythonw.exe -m joapp` (`pythonw` rather than
`python`, so no console window flashes up). The shortcut script wires this up and uses
`joapp/resources/jo-app.ico`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1 -StartMenu  # also add to Start menu
powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1 -Remove     # remove
```

The icon is drawn with QPainter in `joapp/ui/style.py`. To re-export it after changing colours:

```powershell
.\.venv\Scripts\python.exe scripts\make_icon.py
```

### Start with Windows (from source)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_startup.ps1
```

This puts a shortcut to `pythonw.exe -m joapp` in the Startup folder. To undo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_startup.ps1
```

## Configuration

`config.json` is created in the data folder on first run:

| Platform | Location |
|---|---|
| Windows | `%APPDATA%\jo-app\` |
| Others | `~/.jo-app/` |

```jsonc
{
  "remind_enabled": true,                          // start the reminder with the app
  "remind_minutes": 60,                            // interval
  "remind_voice": "喝水时间到了，顺便起来活动一下吧", // spoken text; "" = don't speak
  "remind_popup": "休息下吧",                       // popup text; "" = no popup
  "language": "auto",                              // auto (follow Windows) / zh / en
  "pinned": false,                                 // main window always on top (📌)
  "collapsed": ["yearly"]                          // folded groups
}
```

While `remind_voice` / `remind_popup` hold their default values, the reminder uses the default
text *for the current language*. Put your own text there to override it in both languages.
Restart the app after editing.

Also in that folder: `jo.db` is the database (plain SQLite; query it however you like), and
`reminder.log` is the reminder process's output. Look there if it didn't start.

### Upgrading from the first version

Unfinished tasks from the first version (the one that talked to Claude and planned by the day)
are moved into **Today** the first time the new version starts. They keep their original date,
so they show how many days overdue they are. The old table is left untouched in the database.
Old keys in `config.json` (`llm_enabled`, `focus_minutes`, …) are kept too but no longer read.

## Project layout

```
joapp/
├─ config.py        config read / write
├─ i18n.py          中文 / English: t(), date formats, default reminder text
├─ reminder.py      background reminder process: script, spawn, Job Object, status
├─ core/
│  ├─ models.py     Scope (the four groups) / Todo / Reward / Activity / periods
│  ├─ stats.py      pure math for the activity graph: grid, shades, streaks
│  └─ store.py      SQLite persistence, hand-written SQL
└─ ui/
   ├─ app.py        wiring, single instance, language switching, clean shutdown
   ├─ window.py     main window
   ├─ rewards.py    rewards dialog + "reward earned" popup
   ├─ activity.py   activity graph + day details
   ├─ tray.py       tray icon
   └─ style.py      QSS theme + generated icon
```

Design notes and trade-offs: [docs/DESIGN.md](docs/DESIGN.md).

## Development

```powershell
pip install -e ".[dev]"
pytest
```

The reminder tests really start PowerShell processes (Windows only), but with a 10-hour interval
and no popup, so running the tests makes no sound and shows no box.
`tests/test_i18n.py` parses the source and fails if any `t("…")` string lacks an English translation.

### Building and releasing

```powershell
# Local build: exe in build\dist\jo-app\, installer in dist\jo-app-setup.exe (needs Inno Setup 7)
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -NoInstaller   # exe only
```

To release: bump the version in `joapp/__init__.py` and `pyproject.toml`, commit, then push a
matching tag:

```powershell
git tag v0.6.0
git push origin v0.6.0
```

GitHub Actions (`.github/workflows/release.yml`) runs the tests, builds with the same `build.ps1`,
and publishes `jo-app-setup.exe` to Releases. It fails if the tag doesn't match the version in the code.

## License

MIT
