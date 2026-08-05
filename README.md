# jo-app

> if you joke yourself, you are joker of course.

一个常驻 Windows 托盘的个人规划助手。开机弹一个小窗问你今天打算干什么，
把你的口语回答拆成任务清单，然后在这一天里盯着你 —— 干太久了喊你休息，
走神太久了叫你回来，离 deadline 还有多远也会按时报给你。

没有云端、没有账号、没有订阅。数据全在本地一个 SQLite 文件里。

---

## 它长什么样

```
开机
  ↓
┌─────────────────────────────────┐
│ 今天打算干点什么？               │
│ ┌─────────────────────────────┐ │
│ │ 上午写完季度报告，下午看两章  │ │
│ │ 书，晚上跑个步               │ │
│ └─────────────────────────────┘ │
│              [待会儿再说] [排一下]│
└─────────────────────────────────┘
  ↓ 拆解
┌─────────────────────────────────┐
│ 这样排行吗？                     │
│ 3 件事，预计 200 分钟 · Claude 拆的│
│  ☑ 写完季度报告      ·  120 分钟 │
│  ☑ 读书第 3-4 章     ·   50 分钟 │
│  ☑ 跑步 5 公里       ·   30 分钟 │
│ 上午排得有点满，报告可能要拆成两段 │
│                   [重说] [就这样] │
└─────────────────────────────────┘

……45 分钟后，右下角

┌──────────────────────────────┐
│ 已经连着干了 47 分钟了         │
│ 起来走两步，喝口水，5 分钟后   │
│ 我叫你。                      │
│         [再战 10 分钟] [好，休息]│
└──────────────────────────────┘
```

## 两种输入模式

拆任务这件事，接没接 Claude 差别很大，所以界面会**明说现在是哪种模式**，
而不是让你猜为什么拆得奇怪。

**连上 Claude —— 随便说**

```
上午写完季度报告，下午看两章书，晚上跑个步
```

**没连上 —— 一行一件事，行尾可以写时长**

```
写完季度报告 2小时
读书第 3-4 章 50分钟
跑步 5 公里
```

→ `[写完季度报告 120分] [读书第 3-4 章 50分] [跑步 5 公里 30分]`

离线解析器认这些：时长写 `2小时` / `45分钟` / `1.5h` / `30min` / `（50分钟）`，
不写按 30 分钟算；行首的 `-` `*` `1.` `2、` 会自动去掉。

**不认**的是口语。离线时如果你只写一行，它会退化成按标点硬切
（`上午写完季度报告，下午看两章书` → 两条，但"上午/下午"这些噪音留在标题里，
时长也全是默认值），确认页会直接提示你「整段按标点切的，可能不准」。

这是有意的取舍：规则引擎永远读不懂口语，与其堆一堆启发式然后经常拆错，
不如公开一个简单契约 —— 照着写就一定对。想直接说人话，晨间窗口里有个
「连接 Claude」按钮。

## 它会在什么时候开口

| 场景 | 触发条件 |
|---|---|
| 问今天的计划 | 开机时今天还没录过任何任务 |
| 该休息了 | 连续有输入操作超过 `focus_minutes`（默认 45 分钟） |
| 休息结束 | 休息满 `break_minutes`（默认 5 分钟） |
| 你走神了 | 键鼠无操作超过 20 分钟，且今天还有没做完的事 |
| 离目标还有多远 | 每 4 小时最多一次，挑截止日期最近的那个目标报进度 |
| 晚间复盘 | 到 `evening_review_hour`（默认 22 点），今天有任务 |
| 清单清空 | 今天的任务全部勾完 —— 唯一一条不是催你的提醒 |

每类提醒都有独立的冷却时间，不会连环轰炸。

## 智能层：两条腿走路

```
                  ┌─────────────┐
   状态快照  ───▶ │ rules.py    │ ───▶ 决定「要不要提醒、什么类型」
                  │ 纯函数、离线 │
                  └──────┬──────┘
                         │ 有 API key?
              ┌──────────┴──────────┐
             是                     否
              ▼                     ▼
      ┌───────────────┐      直接用规则文案
      │ llm.py        │
      │ Claude 改写文案│
      │ + 拆解任务     │
      └───────────────┘
```

**要不要提醒永远由本地规则决定**，模型只负责两件事：把你的口语拆成任务，
以及把机械的提醒文案改写得像人说的。所以断网、没 key、API 出错的时候，
应用照常工作，只是话说得糙一点。

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

### 接上 Claude（可选）

不接也能跑，接了提醒会更像人话，任务拆解也更准。两条路，选一条：

**① 浏览器登录（推荐）**

```powershell
ant auth login
```

装了 [ant CLI](https://github.com/anthropics/anthropic-cli/releases) 之后跑这一句，
浏览器里点确认，凭据落到 `%APPDATA%\Anthropic\credentials\`，SDK 会自动读到 ——
**不需要设任何环境变量**。存的是会自动刷新的短期 token，不是一个永久明文密钥。

也可以直接在 jo-app 里点：托盘菜单 →「连接 Claude…」，或者今日面板左下角那个按钮。
登录完不用重启，应用每 20 秒会重新探测一次凭据。

**② 环境变量**

```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."
```

> ⚠️ **两个一起用的时候环境变量赢。** 已经登录过、又设了 `ANTHROPIC_API_KEY`，
> 那 profile 就被架空了。更阴的是**空字符串也算数** —— `ANTHROPIC_API_KEY=""`
> 照样占住优先级，然后拿着空 key 去请求。想用登录凭据就把这个变量**彻底删掉**，
> 不是设成空。今日面板会在检测到这种情况时直接告诉你。

**关于「用 Claude 账号登录」**：上面的 `ant auth login` 是**你自己**在**你自己机器上**
拿 API 凭据。Anthropic 没有那种「让第三方 App 借用终端用户 Claude 订阅额度」的
OAuth ——  Pro/Max 订阅不覆盖 API 调用。所以如果你把 jo-app 发给别人，
每个人还是得自带凭据，或者你自己搭个后端代理。

### 设成开机自启

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_startup.ps1
```

会在「启动」文件夹放一个指向 `pythonw.exe -m joapp` 的快捷方式 ——
用 `pythonw` 是为了开机时不闪黑框。取消：

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
  "focus_minutes": 45,           // 干多久喊你休息
  "break_minutes": 5,            // 休息多久喊你回来
  "idle_threshold_minutes": 5,   // 无输入超过这么久就不算在专注时长里
  "morning_prompt_hour": 0,      // 0 = 开机就问；设 8 就是 8 点后才问
  "evening_review_hour": 22,     // 晚间复盘时间
  "llm_enabled": true,           // 关掉就强制走本地规则
  "model": "claude-opus-5",
  "effort": "medium",            // low | medium | high | xhigh | max
  "nudge_seconds": 12            // 提醒气泡停留时长
}
```

`llm_enabled` 只表示「我愿不愿意用」；有没有凭据是另一回事，由 `agent/auth.py`
探测。凭据本身**永远不会**写进这个文件 —— 要么在环境变量里，要么在
`%APPDATA%\Anthropic\` 由 ant CLI 管。

数据库在同目录的 `jo.db`，标准 SQLite，想自己写脚本查随便查。

## 项目结构

```
joapp/
├─ config.py          配置读写
├─ core/
│  ├─ models.py       Task / Goal / WorkSession / Nudge
│  └─ store.py        SQLite 持久化，手写 SQL
├─ agent/
│  ├─ rules.py        规则引擎（纯函数，离线可用）
│  ├─ parse.py        离线解析器：一行一件事 + 行尾时长
│  ├─ auth.py         凭据探测：登录 profile / 环境变量 / 什么都没有
│  ├─ llm.py          Claude API 客户端，失败即降级
│  ├─ prompts.py      提示词与 JSON schema
│  └─ planner.py      统一入口，规则与模型的编排
├─ scheduler/
│  ├─ activity.py     空闲检测（Win32 GetLastInputInfo）
│  └─ timer.py        专注时长状态机（不依赖 Qt，可测）
└─ ui/
   ├─ app.py          装配与主循环
   ├─ morning.py      晨间提问窗
   ├─ nudge.py        右下角提醒气泡
   ├─ board.py        今日面板
   ├─ tray.py         托盘
   └─ style.py        QSS 主题 + 程序生成的图标
```

## 隐私

- 空闲检测用的是 Win32 `GetLastInputInfo`，只拿「距上次输入多少毫秒」这一个数字，
  不装键盘钩子，不知道你按了什么。
- 开启 LLM 时，发给 Anthropic 的只有：你主动输入的那段计划描述、任务标题、
  目标标题与进度数字。不发文件、不发截图、不发窗口标题。
- 关掉 `llm_enabled` 就完全不联网。

## 开发

```powershell
pip install -e ".[dev]"
pytest
```

规则引擎和存储层有测试覆盖，都不需要 Qt 或网络。

## 路线图

- [ ] 任务与番茄钟绑定：选中一个任务再开始计时，时间自动记到它头上
- [ ] 周报：把一周的专注时长和完成率画出来
- [ ] 目标进度自动推导 —— 完成关联任务时自动 bump
- [ ] PyInstaller 打包成单个 exe
- [ ] 全局热键呼出快速记录

## License

MIT
