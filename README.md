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

不填也能跑，填了提醒会更像人话，任务拆解也更准。

```powershell
# 当前会话
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 或者永久写进用户环境变量
setx ANTHROPIC_API_KEY "sk-ant-..."
```

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

API key 只从环境变量读，**不会**写进这个文件。

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
