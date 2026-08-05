"""领域模型。全部是普通 dataclass，Store 负责持久化。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class TaskStatus(str, Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    DROPPED = "dropped"


@dataclass
class Task:
    """今天要做的一件事。"""

    id: int | None = None
    title: str = ""
    day: date = field(default_factory=date.today)
    status: TaskStatus = TaskStatus.TODO
    estimate_minutes: int = 30  # 预估耗时，用于安排番茄钟
    spent_minutes: int = 0
    goal_id: int | None = None  # 关联到哪个长期目标
    note: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    done_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.status in (TaskStatus.TODO, TaskStatus.DOING)


@dataclass
class Goal:
    """长期目标。用来回答「离最终目标还有多远」。"""

    id: int | None = None
    title: str = ""
    deadline: date | None = None
    target: float = 100.0  # 目标量（可以是页数、章节数、题目数……）
    progress: float = 0.0  # 已完成量
    unit: str = "%"
    archived: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def percent(self) -> float:
        if self.target <= 0:
            return 0.0
        return max(0.0, min(100.0, self.progress / self.target * 100.0))

    @property
    def days_left(self) -> int | None:
        if self.deadline is None:
            return None
        return (self.deadline - date.today()).days

    @property
    def required_pace(self) -> float | None:
        """按剩余天数算，每天还需要推进多少。"""
        days = self.days_left
        if days is None or days <= 0:
            return None
        return (self.target - self.progress) / days


@dataclass
class WorkSession:
    """一段专注时间。"""

    id: int | None = None
    task_id: int | None = None
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    kind: str = "focus"  # focus | break
    interrupted: bool = False

    @property
    def minutes(self) -> float:
        end = self.ended_at or datetime.now()
        return (end - self.started_at).total_seconds() / 60.0


class NudgeKind(str, Enum):
    BREAK = "break"  # 该休息了
    RESUME = "resume"  # 休息结束，回来干活
    GOAL = "goal"  # 目标进度提醒
    IDLE = "idle"  # 你走神/离开很久了
    PLAN = "plan"  # 该定今天的计划了
    REVIEW = "review"  # 该复盘了
    CHEER = "cheer"  # 单纯鼓励一下


@dataclass
class Nudge:
    """一条要弹给用户的提醒。规则引擎和 LLM 都产出这个类型。"""

    kind: NudgeKind
    title: str
    body: str = ""
    actions: list[str] = field(default_factory=list)  # 按钮文案
    source: str = "rules"  # rules | llm
    created_at: datetime = field(default_factory=datetime.now)
