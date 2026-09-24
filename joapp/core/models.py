"""领域模型。全部是普通 dataclass，Store 负责持久化。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Scope(str, Enum):
    """任务按周期分四组。

    每天 / 每周 / 每年是循环的：勾掉只算这一个周期，到下一天 / 周 / 年自动变回没做。
    当天是一次性的：记在哪天就是哪天的事，没做完会一直挂着，直到勾掉或删掉。
    """

    DAILY = "daily"
    TODAY = "today"
    WEEKLY = "weekly"
    YEARLY = "yearly"

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    Scope.DAILY: "每天",
    Scope.TODAY: "当天",
    Scope.WEEKLY: "每周",
    Scope.YEARLY: "每年",
}


def period_key(scope: Scope, today: date, day: date | None = None) -> str:
    """完成记录按周期存。同一个周期内勾一次就算做完了。"""
    if scope is Scope.DAILY:
        return today.isoformat()
    if scope is Scope.WEEKLY:
        year, week, _ = today.isocalendar()
        return f"{year}-W{week:02d}"
    if scope is Scope.YEARLY:
        return str(today.year)
    return (day or today).isoformat()  # 当天任务：属于它自己那一天


@dataclass
class Todo:
    id: int | None = None
    title: str = ""
    scope: Scope = Scope.TODAY
    day: date = field(default_factory=date.today)  # 加进来的那天
    created_at: datetime = field(default_factory=datetime.now)
    done: bool = False  # 当前周期里做完了没（读出来时由 Store 算好）

    def overdue_days(self, today: date) -> int:
        """当天任务拖了几天。其他分组没有「拖」这回事，恒为 0。"""
        if self.scope is not Scope.TODAY or self.done:
            return 0
        return max(0, (today - self.day).days)
