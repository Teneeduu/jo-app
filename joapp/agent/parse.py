"""离线拆解：没有 Claude 时用的本地解析器。

设计取向跟 LLM 那条路相反 —— **不猜，只认格式**。

规则引擎永远读不懂「上午顺手把报告收个尾」，与其做一堆启发式然后经常拆错，
不如公开一个简单契约：一行一件事，行尾可以写时长。用户照着写就一定对，
写不对也能一眼看出哪里没对上。真想说口语，那是连 Claude 的理由。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_MINUTES = 30
MIN_MINUTES = 5
MAX_MINUTES = 240

# 行首的项目符号 / 序号：- * • · 1. 1、 1) (1) 【1】
_BULLET = re.compile(r"^\s*(?:[-*•·◦▪]|\(\d+\)|\[\d+\]|【\d+】|\d+\s*[.、)．]）?)\s*")

# 行尾时长：45分钟 / 45分 / 1小时 / 1.5h / 30min / (2h) / ×90
_DURATION = re.compile(
    r"[（(\[【]?\s*[x×*]?\s*(\d+(?:[.．]\d+)?)\s*"
    # 故意不认单独的 m —— 「跑步5000m」是米不是分钟
    r"(分钟|分鐘|分|min(?:ute)?s?|小时|小時|時|时|h(?:our)?s?|hr)\s*"
    r"[)）\]】]?\s*$",
    re.IGNORECASE,
)
_HOUR_UNITS = {"小时", "小時", "時", "时", "h", "hour", "hours", "hr", "hrs"}

# 单行输入时才用的兜底切分。只切明确的分隔符和连接词 ——
# 故意不切「再」，因为「再战」「再看一遍」里的「再」不是分隔符。
_FALLBACK_SPLIT = re.compile(r"[\n；;。]+|，(?=[^，]{3,})|,(?=[^,]{3,})|然后|接着|之后")

# 收尾时要削掉的残留标点
_TRIM = " \t　-—–·、,，.。;；:：!！?？"


@dataclass
class ParsedTask:
    title: str
    minutes: int = DEFAULT_MINUTES
    explicit_minutes: bool = False  # 时长是用户写的还是默认值


def parse_plan(raw: str) -> list[ParsedTask]:
    """把一段文本拆成任务。

    多行 → 一行一件事（推荐写法，最准）。
    单行 → 按分隔符和连接词兜底切一刀（可能拆得不好，界面上会提示）。
    """
    lines = [ln for ln in (l.strip() for l in raw.splitlines()) if ln]

    if len(lines) >= 2:
        chunks = lines
    else:
        chunks = _FALLBACK_SPLIT.split(raw)

    out: list[ParsedTask] = []
    for chunk in chunks:
        task = _parse_one(chunk)
        if task is not None:
            out.append(task)
    return out


def used_fallback_split(raw: str) -> bool:
    """是否走了不太可靠的单行切分 —— 界面据此决定要不要多说一句。"""
    return len([ln for ln in raw.splitlines() if ln.strip()]) < 2


def _parse_one(chunk: str) -> ParsedTask | None:
    text = _BULLET.sub("", chunk).strip()
    if not text:
        return None

    minutes, explicit = DEFAULT_MINUTES, False
    match = _DURATION.search(text)
    if match:
        minutes = _to_minutes(match.group(1), match.group(2))
        explicit = True
        text = text[: match.start()]

    title = text.strip(_TRIM).strip()
    if len(title) < 2:
        return None
    return ParsedTask(title=title, minutes=minutes, explicit_minutes=explicit)


def _to_minutes(number: str, unit: str) -> int:
    try:
        value = float(number.replace("．", "."))
    except ValueError:
        return DEFAULT_MINUTES
    if unit.lower() in _HOUR_UNITS:
        value *= 60
    return max(MIN_MINUTES, min(MAX_MINUTES, round(value)))
