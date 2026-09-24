# jo-app

> if you joke yourself, you are joker of course.

一个常驻 Windows 托盘的任务清单 + 定时休息提醒。

- **纯离线**：没有云端、没有账号、不联网。数据全在本地一个 SQLite 文件里。
- **加任务就是打一行字**：不估时间、不拆解，回车记下。
- **四个分组一个窗口**：每天 / 当天 / 每周 / 每年，都摆在一起，每组可以折叠。
- **定时提醒**：打开应用就在后台每小时念一句「喝水时间到了，顺便起来活动一下吧」，
  同时弹一个「休息下吧」的框。退出应用，提醒一起关。

---

## 它长什么样

```
┌──────────────────────────────────────────┐
│ jo-app                9月24日 周四 · 第39周 │
│ ┌──────────────────────────────────────┐ │
│ │ 加个任务，回车记下                    │ │
│ └──────────────────────────────────────┘ │
│ [每天] [当天] [每周] [每年]         [添加] │
│                                          │
│ ▾ 每天   1/3                              │
│   ☑ 喝够 8 杯水                        ×  │
│   ☐ 背 20 个单词                       ×  │
│   ☐ 晚上拉伸 10 分钟                   ×  │
│ ▾ 当天   0/2                              │
│   ☐ 交季度报告           拖了 2 天     ×  │
│   ☐ 给妈妈打电话                       ×  │
│ ▾ 每周   0/1                              │
│   ☐ 打扫房间                           ×  │
│ ▸ 每年   0/1              ← 点标题折叠/展开 │
│──────────────────────────────────────────│
│ 提醒：每 [60 分钟]           [试一下] [暂停] │
│ ● 提醒在后台运行 · 每 60 分钟提醒一次  [退出] │
└──────────────────────────────────────────┘
```

## 四个分组

| 分组 | 是什么 | 勾掉之后 |
|---|---|---|
| **每天** | 每天都要做的事 | 只算今天，明天自动变回没做 |
| **当天** | 一次性的事，记在哪天就是哪天的 | 做完第二天就不显示了；**没做完会一直挂着**，标出「拖了 N 天」 |
| **每周** | 每周要做一次的事 | 这一周都算做完，下周一变回没做 |
| **每年** | 每年要做一次的事 / 年度目标 | 今年都算做完，明年变回没做 |

- 加任务：输入框打字 → 选分组（默认「当天」，也可以 `Ctrl+1`~`Ctrl+4` 切）→ 回车。
- 删任务：点行尾的 `×`，会确认一下。
- 折叠：点分组标题。折叠状态会记住，**但「每天」每次打开都会展开** ——
  每天的事每次打开都得看见。

## 打开和关闭

- **打开应用**：窗口直接弹出来，同时后台拉起定时提醒。
- **已经开着再双击一次快捷方式**：把托盘里那个窗口叫出来（不会开第二个）。
- **点窗口右上角的 ×**：窗口缩回托盘，**提醒照常**。点托盘图标再打开。
- **点「退出」按钮 / 托盘右键 →「退出」**：应用退出，**后台提醒一起关**。

## 定时提醒

打开应用时自动在后台跑，相当于这两段 PowerShell 合在一起：

```powershell
# 每小时念一句
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
while ($true) { Start-Sleep -Seconds 3600; $s.Speak("喝水时间到了，顺便起来活动一下吧") }

# 弹个框
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show("休息下吧", "提示")
```

实际跑的时候：每到点**同时**念那句话、弹「休息下吧」的框（框会盖在其他窗口上面）。
你点掉弹框之后才开始算下一个小时 —— 人不在电脑前的话，回来只会看到一个框，
不会攒一堆。

和直接用 `Start-Process powershell -WindowStyle Hidden ...` 的区别：

- **退出应用时一定会关掉**。`Start-Process` 起的进程跟应用断了关系，
  应用退了它还在后台一小时念一次，只能去任务管理器里找。这里的提醒进程挂在
  一个 Windows Job Object 上，应用**正常退出、崩溃、被任务管理器结束**，
  提醒进程都会跟着被系统杀掉。
- **有中文语音就用中文语音**。系统默认语音可能是英文的（Microsoft Zira），
  念中文会乱读或者没声音；有 Microsoft Huihui 这类中文语音就自动换上。
- **跑没跑起来看得见**。窗口底部显示状态：绿色「● 提醒在后台运行」是好的；
  红色「✕ 提醒没跑起来：……」会带上 PowerShell 的报错原文，托盘也会弹通知。
- **「试一下」**：立刻念一遍、弹一次框，确认有声音、框能弹出来。

间隔在窗口底部直接改（改完从现在重新计时）；「暂停」/「开启」切换提醒，都会记住。

## 安装

需要 Python 3.10+。

```powershell
git clone https://github.com/Teneeduu/jo-app.git
cd jo-app

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m joapp
```

### 桌面快捷方式

jo-app **没有独立的 exe** —— 它跑在 `pythonw.exe -m joapp` 上（用 `pythonw`
而不是 `python`，双击时才不会弹黑框）。快捷方式脚本会把这些接好，图标用
`joapp/resources/jo-app.ico`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1 -StartMenu  # 顺带放开始菜单
powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1 -Remove     # 删掉
```

图标是 `joapp/ui/style.py` 里用 QPainter 画的，改了配色重新导出：

```powershell
.\.venv\Scripts\python.exe scripts\make_icon.py
```

### 设成开机自启

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_startup.ps1
```

会在「启动」文件夹放一个指向 `pythonw.exe -m joapp` 的快捷方式。取消：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_startup.ps1
```

## 配置

首次运行会在数据目录生成 `config.json`：

| 平台 | 位置 |
|---|---|
| Windows | `%APPDATA%\jo-app\` |
| 其他 | `~/.jo-app/` |

```jsonc
{
  "remind_enabled": true,                          // 打开应用就启动提醒
  "remind_minutes": 60,                            // 间隔
  "remind_voice": "喝水时间到了，顺便起来活动一下吧", // 念的话，空串 = 不念
  "remind_popup": "休息下吧",                       // 弹框文字，空串 = 不弹
  "collapsed": ["yearly"]                          // 折叠着的分组
}
```

改了念的话 / 弹框文字之后重启应用生效。

同目录下：`jo.db` 是数据库（标准 SQLite，想自己写脚本查随便查），
`reminder.log` 是提醒进程的输出，没跑起来时看这里。

### 从旧版本升级

旧版本（接 Claude、按天排计划那一版）里**没做完**的任务，第一次打开新版时
会自动搬成「当天」任务（带着原来的日期，所以会显示拖了几天）。旧表原样留在库里
没删。`config.json` 里旧的键（`llm_enabled`、`focus_minutes`……）也原样留着，
新版不读它们。

## 项目结构

```
joapp/
├─ config.py        配置读写
├─ reminder.py      后台提醒进程：拼脚本、起进程、Job Object、状态
├─ core/
│  ├─ models.py     Scope（四个分组）/ Todo / 周期
│  └─ store.py      SQLite 持久化，手写 SQL
└─ ui/
   ├─ app.py        装配、单实例、退出时收尾
   ├─ window.py     主窗口
   ├─ tray.py       托盘
   └─ style.py      QSS 主题 + 程序生成的图标
```

## 开发

```powershell
pip install -e ".[dev]"
pytest
```

提醒的测试会真的起 PowerShell 进程（只在 Windows 上跑），但间隔设成 10 小时、
不弹框，跑测试时不会出声也不会弹窗。

## License

MIT
