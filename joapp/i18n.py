"""界面语言：中文 / English。

用法：`t("完成 {done}/{total}", done=1, total=3)`。中文原文就是 key ——
代码里读起来还是中文，英文模式下查 EN 表。表里没有的 key 原样返回中文，
tests/test_i18n.py 会扫一遍源码，保证每个 t("...") 都有英文。

不依赖 Qt，models / reminder 里也能用。
"""

from __future__ import annotations

import ctypes
import locale
import os
from datetime import date, datetime

LANGUAGES = ("zh", "en")
_lang = "zh"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGUAGES else "zh"


def language() -> str:
    return _lang


def resolve(setting: str) -> str:
    """配置里的 "auto" / "zh" / "en" → 实际用哪个。auto 跟系统界面语言走。"""
    return setting if setting in LANGUAGES else system_language()


def system_language() -> str:
    if os.name == "nt":
        try:
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "zh" if (lang_id & 0x3FF) == 0x04 else "en"  # 0x04 = LANG_CHINESE
        except (AttributeError, OSError):
            pass
    name = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    return "zh" if name.startswith(("zh", "chinese")) else "en"


def t(zh: str, **kwargs) -> str:
    text = zh if _lang == "zh" else EN.get(zh, zh)
    return text.format(**kwargs) if kwargs else text


# ---------- 日期 ----------

_EN_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
_EN_WEEKDAYS = "Mon Tue Wed Thu Fri Sat Sun".split()
_ZH_WEEKDAYS = "一二三四五六日"


def month_short(month: int) -> str:
    return f"{month}月" if _lang == "zh" else _EN_MONTHS[month - 1]


def weekday_short(index: int) -> str:
    """0 = 周一。"""
    return _ZH_WEEKDAYS[index] if _lang == "zh" else _EN_WEEKDAYS[index]


def day_text(d: date) -> str:
    if _lang == "zh":
        return f"{d.month}月{d.day}日 周{_ZH_WEEKDAYS[d.weekday()]}"
    return f"{_EN_WEEKDAYS[d.weekday()]}, {_EN_MONTHS[d.month - 1]} {d.day}"


def date_line(d: date) -> str:
    week = d.isocalendar()[1]
    if _lang == "zh":
        return f"{day_text(d)} · 第{week}周"
    return f"{day_text(d)} · Week {week}"


def round_since(started: datetime) -> str:
    stamp = f"{started.month}/{started.day} {started:%H:%M}"
    return f"{stamp} 起" if _lang == "zh" else f"since {stamp}"


# ---------- 定时提醒的默认文字 ----------
# 用户没改过就跟着界面语言走；改过（不等于任何一种默认值）就原样用。

DEFAULT_VOICE = {
    "zh": "喝水时间到了，顺便起来活动一下吧",
    "en": "Time for some water. Get up and move around a bit.",
}
DEFAULT_POPUP = {"zh": "休息下吧", "en": "Take a break."}
POPUP_TITLE = {"zh": "提示", "en": "Reminder"}
VOICE_CULTURE = {"zh": "zh", "en": "en"}  # 选哪种语音（Culture 前缀）


def reminder_text(configured: str, defaults: dict[str, str]) -> str:
    return defaults[_lang] if configured in defaults.values() else configured


# ---------- 英文表 ----------

EN: dict[str, str] = {
    # 分组
    "每天": "Daily",
    "当天": "Today",
    "每周": "Weekly",
    "每年": "Yearly",
    # 主窗口
    "↻ 重新开始": "↻ New round",
    "每天任务全部变回没做，每天的奖励可以重新拿": "Uncheck all daily tasks and make daily rewards available again",
    "还没有": "Nothing yet",
    "这一轮从 {when} 开始": "This round started {when}",
    "拖了 {n} 天": "{n}d overdue",
    "删除": "Delete",
    "加个任务，回车记下": "Add a task, press Enter",
    "添加": "Add",
    "提醒：每": "Remind every",
    " 分钟": " min",
    "试一下": "Try it",
    "立刻念一遍、弹一次框": "Speak and pop up once, right now",
    "暂停": "Pause",
    "开启": "Resume",
    "📅 记录": "📅 Activity",
    "活动记录：像 GitHub 那样看每天做了哪些事": "Activity: see what you got done each day, GitHub style",
    "🎁 奖励": "🎁 Rewards",
    "给每天 / 每周 / 每年的完成度设奖励": "Set rewards for daily / weekly / yearly progress",
    "退出": "Quit",
    "退出 jo-app，后台提醒一起关掉": "Quit jo-app and stop the background reminder",
    "重新开始": "New round",
    "开始新一轮每天任务？\n\n这一轮做完了 {done}/{total} 件。重新开始后：\n· 每天任务全部变回没做\n· 每天的奖励可以重新拿\n\n当天 / 每周 / 每年的不受影响。": (
        "Start a new round of daily tasks?\n\n"
        "Done this round: {done}/{total}. After starting over:\n"
        "· All daily tasks are unchecked\n"
        "· Daily rewards can be earned again\n\n"
        "Today / weekly / yearly tasks are not affected."
    ),
    "删除任务": "Delete task",
    "删掉「{title}」？": "Delete \"{title}\"?",
    "\n\n这是{scope}都会出现的任务，删了以后就不再出现。": "\n\nThis is a recurring {scope} task. Once deleted, it won't come back.",
    "提醒已暂停": "Reminder paused",
    "● 提醒在后台运行 · {detail}": "● Reminder running · {detail}",
    "✕ 提醒没跑起来：{detail}": "✕ Reminder failed to start: {detail}",
    # 奖励
    "给自己的奖励": "Rewards",
    "完成到多少，奖励自己什么": "Reward yourself when you get there",
    "每个奖励每个周期只发一次：每天的按「重新开始」后重来，每周的下周一重来，每年的明年重来。": (
        "Each reward is given once per period: daily ones again after \"New round\", "
        "weekly ones next Monday, yearly ones next year."
    ),
    "分组": "Group",
    "完成到": "When done reaches",
    "奖励自己……比如「看一集剧」「买杯奶茶」": "Treat yourself… e.g. \"watch an episode\"",
    "完成": "Done",
    "还没设奖励。在下面加一个。": "No rewards yet. Add one below.",
    "{scope}完成 {percent}%   →   {text}": "{scope} {percent}%   →   {text}",
    "这期已拿到": "Earned this period",
    "删除这个奖励": "Delete this reward",
    "拿到奖励了": "Reward earned",
    "🎉 {scope}任务完成了 {done}/{total}": "🎉 {scope} tasks: {done}/{total} done",
    "达到 {percent}%  →  <b>{text}</b>": "Reached {percent}%  →  <b>{text}</b>",
    "去兑现吧，这是你自己挣的。": "Go enjoy it — you earned it.",
    "收下": "Thanks!",
    # 活动记录
    "jo-app · 活动记录": "jo-app · Activity",
    "{day} · 完成 {n} 件": "{day} · {n} done",
    "{day} · 没有记录": "{day} · nothing recorded",
    "少": "Less",
    "多": "More",
    "过去一年": "Past year",
    "过去一年完成了 {total} 件事": "{total} things done in the past year",
    "{year} 年完成了 {total} 件事": "{total} things done in {year}",
    "当前连续 {current} 天 · 最长连续 {longest} 天": "Current streak {current} days · Longest {longest} days",
    "今天": "Today",
    "🎁 拿到奖励：{title}": "🎁 Reward earned: {title}",
    "（{scope}）": " ({scope})",
    "[旧版] ": "[old] ",
    # 托盘
    "打开清单": "Open list",
    "活动记录": "Activity",
    "试一下提醒": "Try the reminder",
    "暂停提醒": "Pause reminder",
    "开启提醒": "Resume reminder",
    "退出（提醒一起关）": "Quit (stops the reminder)",
    "提醒没跑起来": "Reminder failed to start",
    "jo-app 还在托盘里": "jo-app is still in the tray",
    "提醒照常。要彻底退出，右键托盘图标 →「退出」。": "Reminders keep running. To quit, right-click the tray icon → Quit.",
    # 提醒进程
    "只支持 Windows": "Windows only",
    "念的话和弹窗文字都是空的，没什么可提醒的": "Both the spoken text and the popup text are empty — nothing to remind you of",
    "启动 PowerShell 失败：{error}": "Failed to start PowerShell: {error}",
    "后台进程退出了（代码 {code}）": "Background process exited (code {code})",
    "：{tail}": ": {tail}",
    "每 {n} 分钟提醒一次": "every {n} min",
    "这台电脑没有{lang}语音（用的是 {voice}），可能念不清楚": "no {lang} voice on this PC (using {voice}), speech may be unclear",
    "中文": "Chinese",
    "英文": "English",
    "正在启动……": "Starting…",
}
