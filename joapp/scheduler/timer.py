"""专注时长跟踪。刻意不依赖 Qt —— 由外部按固定间隔喂 tick，方便测试。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Phase(str, Enum):
    AWAY = "away"  # 人不在
    FOCUS = "focus"  # 正在干活
    BREAK = "break"  # 主动休息中


@dataclass
class FocusTracker:
    """把「时间流逝 + 是否有输入」翻译成连续专注时长。

    关键点：离开电脑（idle 超阈值）时不累计专注时长，也不清零 ——
    去倒杯水回来还算同一段，走开半小时才重新计。
    """

    idle_threshold_minutes: float = 5.0
    reset_after_away_minutes: float = 20.0

    phase: Phase = Phase.AWAY
    focus_minutes: float = 0.0
    break_minutes: float = 0.0
    away_minutes: float = 0.0
    last_tick: datetime | None = field(default=None)

    def tick(self, idle_minutes: float, now: datetime | None = None) -> Phase:
        """推进状态机。返回当前阶段。"""
        now = now or datetime.now()
        elapsed = 0.0
        if self.last_tick is not None:
            elapsed = (now - self.last_tick).total_seconds() / 60.0
            # 系统休眠 / 时钟跳变，丢弃这一段
            if elapsed < 0 or elapsed > 10:
                elapsed = 0.0
        self.last_tick = now

        if self.phase is Phase.BREAK:
            self.break_minutes += elapsed
            return self.phase

        active = idle_minutes < self.idle_threshold_minutes
        if active:
            if self.phase is Phase.AWAY and self.away_minutes >= self.reset_after_away_minutes:
                self.focus_minutes = 0.0
            self.away_minutes = 0.0
            self.phase = Phase.FOCUS
            self.focus_minutes += elapsed
        else:
            self.phase = Phase.AWAY
            self.away_minutes += elapsed
        return self.phase

    # --- 外部控制 ---

    def start_break(self) -> None:
        self.phase = Phase.BREAK
        self.break_minutes = 0.0
        self.focus_minutes = 0.0

    def end_break(self) -> None:
        self.phase = Phase.FOCUS
        self.break_minutes = 0.0
        self.away_minutes = 0.0

    def snooze(self, minutes: float = 10.0) -> None:
        """「再战 10 分钟」：把专注计时往回拨，推迟下次休息提醒。"""
        self.focus_minutes = max(0.0, self.focus_minutes - minutes)

    def reset(self) -> None:
        self.phase = Phase.AWAY
        self.focus_minutes = 0.0
        self.break_minutes = 0.0
        self.away_minutes = 0.0
        self.last_tick = None
