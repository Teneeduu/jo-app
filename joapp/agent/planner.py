"""规则与 LLM 的统一入口。

上层（UI / 调度器）只跟 Planner 打交道，不关心这次是谁答的。
有 key 就走 Claude，没有 / 失败就落回本地规则，两条路返回同样的类型。
"""

from __future__ import annotations

import logging
from datetime import date

from ..config import Config
from ..core.models import Goal, Nudge, Task
from ..core.store import Store
from . import auth, parse
from .llm import LLM, LLMUnavailable
from .rules import Snapshot, evaluate

log = logging.getLogger(__name__)


class Planner:
    def __init__(self, cfg: Config, store: Store):
        self.cfg = cfg
        self.store = store
        self.llm = LLM(cfg)
        self.last_source = "rules"  # 上一次是谁答的，UI 上会标出来
        # 上一次调用为什么失败。凭据没问题但调不通（比如没额度）时，
        # 界面必须说清楚，不能装成「离线模式」让人查错方向。
        self.last_error: LLMUnavailable | None = None

    @property
    def credentials(self) -> auth.Credentials:
        """每次现查 —— 用户可能在应用跑着的时候才去 ant auth login。"""
        return auth.detect()

    @property
    def use_llm(self) -> bool:
        return self.cfg.llm_enabled and self.credentials.available

    @property
    def failing(self) -> bool:
        """有凭据、也愿意用，但上一次调不通。"""
        return self.use_llm and self.last_error is not None

    @property
    def llm_working(self) -> bool:
        """界面据此决定给「随便说」还是「按格式写」的提示。

        第一次调用之前无从知道通不通，所以默认乐观；失败过一次之后就转成
        离线提示 —— 与其让用户对着「随便说」反复得到烂结果，不如老实换契约。
        """
        return self.use_llm and self.last_error is None

    @property
    def status_line(self) -> str:
        """一句话说清现在到底是什么状态，给界面直接显示。"""
        if not self.cfg.llm_enabled:
            return "Claude：配置里关掉了，全部走本地规则"
        creds = self.credentials
        if not creds.available:
            return f"Claude：{creds.detail} —— 现在提醒由本地规则生成"
        if self.last_error is not None:
            return f"Claude：{creds.detail}，但调用失败 —— {self.last_error.hint}"
        return f"Claude：{creds.detail}"

    # ---------- 把一段话变成任务 ----------

    def plan_from_text(self, raw: str, day: date | None = None) -> tuple[list[Task], str]:
        """返回 (任务列表, 一句点评)。任务还没入库，交给调用方确认后再存。"""
        day = day or date.today()
        goals = self.store.goals()
        if self.use_llm:
            try:
                result = self.llm.plan_tasks(raw, [g.title for g in goals])
                self.last_source = "llm"
                self.last_error = None
                return self._to_tasks(result["tasks"], goals, day), result.get(
                    "comment", ""
                )
            except LLMUnavailable as e:
                self.last_error = e
                log.warning("LLM 拆解失败（%s），改用本地规则: %s", e.reason.value, e)

        self.last_source = "rules"
        tasks, comment = self._split_locally(raw, day)
        if tasks and self.failing:
            # 有凭据却调不通 —— 说明白，别让用户以为是「没连上」
            comment = f"Claude 没用上：{self.last_error.hint} 先按本地格式拆的。"
        return tasks, comment

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

    def _split_locally(self, raw: str, day: date) -> tuple[list[Task], str]:
        """没有模型时按格式解析。点评里直接说清楚它是怎么拆的、怎么写更准。"""
        parsed = parse.parse_plan(raw)
        tasks = [
            Task(title=p.title, day=day, estimate_minutes=p.minutes) for p in parsed
        ]
        if not tasks:
            return [], ""

        guessed = sum(1 for p in parsed if not p.explicit_minutes)
        notes = []
        if parse.used_fallback_split(raw):
            notes.append("离线拆的：整段按标点切的，可能不准 —— 一行一件事最稳")
        else:
            notes.append(f"离线拆的：按行分了 {len(tasks)} 条")
        if guessed:
            notes.append(f"其中 {guessed} 条没写时长，先按 {parse.DEFAULT_MINUTES} 分钟算")
        return tasks, "。".join(notes) + "。"

    # ---------- 该不该提醒，提醒说什么 ----------

    def next_nudge(self, snapshot: Snapshot) -> Nudge | None:
        """规则决定「要不要提醒、提醒什么类型」，LLM 只负责把话说好听。"""
        candidates = evaluate(snapshot)
        if not candidates:
            return None
        nudge = candidates[0]

        if self.use_llm:
            try:
                better = self.llm.rewrite_nudge(
                    nudge.kind.value, nudge.title, nudge.body, _context(snapshot)
                )
                nudge.title = better.get("title") or nudge.title
                nudge.body = better.get("body") or nudge.body
                nudge.source = "llm"
                self.last_error = None
            except LLMUnavailable as e:
                self.last_error = e
                log.info("提醒改写失败（%s），用规则原文: %s", e.reason.value, e)

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
