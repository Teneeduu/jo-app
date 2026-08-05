"""规则引擎的测试。规则是纯函数，不需要 Qt、不需要网络。"""

from datetime import date, datetime, timedelta

import pytest

from joapp.config import Config
from joapp.core.models import Goal, NudgeKind, Task, TaskStatus
from joapp.agent.rules import Snapshot, evaluate


def snap(**kw) -> Snapshot:
    base = dict(now=datetime(2026, 8, 5, 14, 0), cfg=Config(), planned_today=True)
    base.update(kw)
    return Snapshot(**base)


def kinds(s: Snapshot) -> set[NudgeKind]:
    return {n.kind for n in evaluate(s)}


def test_break_fires_after_a_full_focus_block():
    cfg = Config(focus_minutes=45)
    assert NudgeKind.BREAK in kinds(snap(cfg=cfg, focus_streak_minutes=46))


def test_break_does_not_fire_early():
    cfg = Config(focus_minutes=45)
    assert NudgeKind.BREAK not in kinds(snap(cfg=cfg, focus_streak_minutes=44))


def test_break_does_not_fire_while_on_break():
    s = snap(focus_streak_minutes=90, on_break=True)
    assert NudgeKind.BREAK not in kinds(s)


def test_resume_fires_when_break_is_over():
    cfg = Config(break_minutes=5)
    s = snap(cfg=cfg, on_break=True, break_elapsed_minutes=6)
    assert NudgeKind.RESUME in kinds(s)


def test_plan_prompt_only_when_nothing_planned():
    assert NudgeKind.PLAN in kinds(snap(planned_today=False))
    assert NudgeKind.PLAN not in kinds(snap(planned_today=True))


def test_idle_needs_open_tasks():
    done = Task(id=1, title="写报告", status=TaskStatus.DONE)
    assert NudgeKind.IDLE not in kinds(snap(idle_minutes=60, tasks=[done]))

    todo = Task(id=2, title="看书")
    assert NudgeKind.IDLE in kinds(snap(idle_minutes=60, tasks=[todo]))


def test_goal_reports_the_nearest_deadline():
    near = Goal(id=1, title="近的", deadline=date(2026, 8, 10), target=100, progress=20)
    far = Goal(id=2, title="远的", deadline=date(2027, 1, 1), target=100, progress=0)
    nudges = [n for n in evaluate(snap(goals=[far, near])) if n.kind is NudgeKind.GOAL]
    assert nudges and "近的" in nudges[0].title


def test_overdue_goal_says_so():
    stale = Goal(id=1, title="拖了的", deadline=date(2026, 8, 1), target=10, progress=1)
    nudge = next(n for n in evaluate(snap(goals=[stale])) if n.kind is NudgeKind.GOAL)
    assert "过期" in nudge.title


def test_cheer_only_when_everything_is_done():
    done = Task(id=1, title="做完了", status=TaskStatus.DONE)
    assert NudgeKind.CHEER in kinds(snap(tasks=[done]))
    assert NudgeKind.CHEER not in kinds(snap(tasks=[done, Task(id=2, title="没做")]))
    assert NudgeKind.CHEER not in kinds(snap(tasks=[]))  # 空清单不算成就


def test_cooldown_suppresses_repeats():
    now = datetime(2026, 8, 5, 14, 0)
    s = snap(
        now=now,
        focus_streak_minutes=90,
        last_nudge={NudgeKind.BREAK: now - timedelta(minutes=2)},
    )
    assert NudgeKind.BREAK not in kinds(s)

    s.last_nudge[NudgeKind.BREAK] = now - timedelta(hours=2)
    assert NudgeKind.BREAK in kinds(s)


def test_goal_percent_and_pace():
    g = Goal(title="读完 300 页", target=300, progress=90, deadline=date(2026, 8, 15))
    assert g.percent == pytest.approx(30.0)
    assert g.days_left == (date(2026, 8, 15) - date.today()).days
