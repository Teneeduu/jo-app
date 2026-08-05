"""规则引擎：不联网、不要 key 也能跑的那一半智能。

设计成纯函数 —— 输入一个 Snapshot，输出若干 Nudge。所有时间相关的状态都由
调用方装进 Snapshot，规则本身不碰时钟，方便测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..config import Config
from ..core.models import Goal, Nudge, NudgeKind, Task

# 同类提醒的最短间隔（分钟），避免连环轰炸
COOLDOWN = {
    NudgeKind.BREAK: 20,
    NudgeKind.GOAL: 240,
    NudgeKind.IDLE: 30,
    NudgeKind.PLAN: 120,
    NudgeKind.REVIEW: 600,
    NudgeKind.CHEER: 180,
}


@dataclass
class Snapshot:
    """某一时刻的全部状态。规则只看这个。"""

    now: datetime
    cfg: Config
    tasks: list[Task] = field(default_factory=list)
    goals: list[Goal] = field(default_factory=list)
    planned_today: bool = False
    focus_streak_minutes: float = 0.0  # 当前这段连续专注了多久
    idle_minutes: float = 0.0  # 键鼠无输入多久
    on_break: bool = False
    break_elapsed_minutes: float = 0.0
    last_nudge: dict[NudgeKind, datetime] = field(default_factory=dict)

    def cooled_down(self, kind: NudgeKind) -> bool:
        last = self.last_nudge.get(kind)
        if last is None:
            return True
        gap = (self.now - last).total_seconds() / 60.0
        return gap >= COOLDOWN.get(kind, 30)


def evaluate(s: Snapshot) -> list[Nudge]:
    """按优先级返回当下该发的提醒。通常调用方只取第一条。"""
    out: list[Nudge] = []
    for rule in (
        _rule_resume_from_break,
        _rule_take_a_break,
        _rule_idle_too_long,
        _rule_plan_the_day,
        _rule_goal_distance,
        _rule_evening_review,
        _rule_cheer,
    ):
        n = rule(s)
        if n is not None and s.cooled_down(n.kind):
            out.append(n)
    return out


# --- 具体规则 ---------------------------------------------------------------


def _rule_take_a_break(s: Snapshot) -> Nudge | None:
    """连续干了一个番茄钟以上，喊停。"""
    if s.on_break or s.focus_streak_minutes < s.cfg.focus_minutes:
        return None
    mins = int(s.focus_streak_minutes)
    return Nudge(
        kind=NudgeKind.BREAK,
        title=f"已经连着干了 {mins} 分钟了",
        body=f"起来走两步，喝口水，{s.cfg.break_minutes} 分钟后我叫你。",
        actions=["好，休息", "再战 10 分钟"],
    )


def _rule_resume_from_break(s: Snapshot) -> Nudge | None:
    if not s.on_break or s.break_elapsed_minutes < s.cfg.break_minutes:
        return None
    nxt = next((t.title for t in s.tasks if t.is_open), None)
    body = f"下一件：{nxt}" if nxt else "今天的清单已经清空了，可以加点新的。"
    return Nudge(
        kind=NudgeKind.RESUME,
        title="休息结束",
        body=body,
        actions=["开始", "再歇 5 分钟"],
    )


def _rule_idle_too_long(s: Snapshot) -> Nudge | None:
    """长时间没动，且今天还有没做完的事。"""
    threshold = max(s.cfg.idle_threshold_minutes * 4, 20)
    if s.on_break or s.idle_minutes < threshold:
        return None
    open_n = sum(1 for t in s.tasks if t.is_open)
    if open_n == 0:
        return None
    return Nudge(
        kind=NudgeKind.IDLE,
        title=f"你走开 {int(s.idle_minutes)} 分钟了",
        body=f"还有 {open_n} 件事挂着。回来收个尾？",
        actions=["回来了", "今天到此为止"],
    )


def _rule_plan_the_day(s: Snapshot) -> Nudge | None:
    if s.planned_today:
        return None
    if s.now.hour < s.cfg.morning_prompt_hour:
        return None
    return Nudge(
        kind=NudgeKind.PLAN,
        title="今天打算干点什么？",
        body="说给我听，我帮你排。",
        actions=["现在就说", "待会儿"],
    )


def _rule_goal_distance(s: Snapshot) -> Nudge | None:
    """挑最紧的那个目标报进度。"""
    urgent = [g for g in s.goals if g.days_left is not None]
    if not urgent:
        return None
    g = min(urgent, key=lambda x: x.days_left)
    days = g.days_left
    if days is None:
        return None
    if days < 0:
        return Nudge(
            kind=NudgeKind.GOAL,
            title=f"「{g.title}」已经过期 {-days} 天",
            body="要么改期，要么今天把它推完。",
            actions=["改个日期", "今天推它"],
        )
    pace = g.required_pace or 0
    return Nudge(
        kind=NudgeKind.GOAL,
        title=f"「{g.title}」还剩 {days} 天",
        body=(
            f"进度 {g.percent:.0f}%，剩下 {g.target - g.progress:.0f}{g.unit}，"
            f"平均每天要推 {pace:.1f}{g.unit}。"
        ),
        actions=["知道了", "更新进度"],
    )


def _rule_evening_review(s: Snapshot) -> Nudge | None:
    if s.now.hour < s.cfg.evening_review_hour:
        return None
    done = sum(1 for t in s.tasks if not t.is_open)
    total = len(s.tasks)
    if total == 0:
        return None
    return Nudge(
        kind=NudgeKind.REVIEW,
        title=f"今天完成 {done}/{total}",
        body="花一分钟看一眼，没做完的顺到明天？",
        actions=["复盘一下", "顺延到明天"],
    )


def _rule_cheer(s: Snapshot) -> Nudge | None:
    """全部做完时给个正反馈 —— 唯一一条不是催你的提醒。"""
    if not s.tasks or any(t.is_open for t in s.tasks):
        return None
    return Nudge(
        kind=NudgeKind.CHEER,
        title="今天的清单清空了",
        body="剩下的时间是你自己的。",
        actions=["收工"],
    )
