"""规则与 LLM 的统一入口。

上层（UI / 调度器）只跟 Planner 打交道，不关心这次是谁答的。
有 key 就走 Claude，没有 / 失败就落回本地规则，两条路返回同样的类型。
"""

from __future__ import annotations

import logging
import re
from datetime import date

from ..config import Config
from ..core.models import Goal, Nudge, Task
from ..core.store import Store
from .llm import LLM, LLMUnavailable
from .rules import Snapshot, evaluate

log = logging.getLogger(__name__)

_SPLIT = re.compile(r"[\n；;,，。]|然后|接着|再")


class Planner:
    def __init__(self, cfg: Config, store: Store):
        self.cfg = cfg
        self.store = store
        self.llm = LLM(cfg)
        self.last_source = "rules"  # 上一次是谁答的，UI 上会标出来

    # ---------- 把一段话变成任务 ----------

    def plan_from_text(self, raw: str, day: date | None = None) -> tuple[list[Task], str]:
        """返回 (任务列表, 一句点评)。任务还没入库，交给调用方确认后再存。"""
        day = day or date.today()
        goals = self.store.goals()
        if self.cfg.use_llm:
            try:
                result = self.llm.plan_tasks(raw, [g.title for g in goals])
                self.last_source = "llm"
                return self._to_tasks(result["tasks"], goals, day), result.get(
                    "comment", ""
                )
            except LLMUnavailable as e:
                log.warning("LLM 拆解失败，改用本地规则: %s", e)
        self.last_source = "rules"
        return self._split_locally(raw, day), ""

    def _to_tasks(self, items: list[dict], goals: list[Goal], day: date) -> list[Task]:
        by_title = {g.title: g.id for g in goals}
        tasks = []
        for item in items:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            tasks.append(
                Task(
                    title=title,
                    day=day,
                    estimate_minutes=_clamp(item.get("estimate_minutes", 30)),
                    goal_id=by_title.get(item.get("goal_title") or ""),
                )
            )
        return tasks

    def _split_locally(self, raw: str, day: date) -> list[Task]:
        """没有模型时的兜底：按标点和连接词切一刀。"""
        parts = [p.strip(" -•\t") for p in _SPLIT.split(raw)]
        return [Task(title=p, day=day) for p in parts if len(p) >= 2]

    # ---------- 该不该提醒，提醒说什么 ----------

    def next_nudge(self, snapshot: Snapshot) -> Nudge | None:
        """规则决定「要不要提醒、提醒什么类型」，LLM 只负责把话说好听。"""
        candidates = evaluate(snapshot)
        if not candidates:
            return None
        nudge = candidates[0]

        if self.cfg.use_llm:
            try:
                better = self.llm.rewrite_nudge(
                    nudge.kind.value, nudge.title, nudge.body, _context(snapshot)
                )
                nudge.title = better.get("title") or nudge.title
                nudge.body = better.get("body") or nudge.body
                nudge.source = "llm"
            except LLMUnavailable as e:
                log.info("提醒改写失败，用规则原文: %s", e)

        self.last_source = nudge.source
        self.store.log_nudge(
            nudge.kind.value, nudge.title, nudge.body, nudge.source
        )
        return nudge


def _clamp(minutes: object, low: int = 5, high: int = 240) -> int:
    try:
        return max(low, min(high, int(minutes)))
    except (TypeError, ValueError):
        return 30


def _context(s: Snapshot) -> str:
    open_tasks = [t for t in s.tasks if t.is_open]
    lines = [
        f"现在 {s.now:%H:%M}",
        f"连续专注 {s.focus_streak_minutes:.0f} 分钟，无操作 {s.idle_minutes:.0f} 分钟",
        f"今天 {len(s.tasks)} 件事，还剩 {len(open_tasks)} 件未完成",
    ]
    for t in open_tasks[:3]:
        lines.append(f"  未完成：{t.title}（预估 {t.estimate_minutes} 分钟）")
    for g in s.goals[:2]:
        days = g.days_left
        left = f"还剩 {days} 天" if days is not None else "无截止日期"
        lines.append(f"  目标「{g.title}」进度 {g.percent:.0f}%，{left}")
    return "\n".join(lines)
