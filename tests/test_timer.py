"""FocusTracker 的测试。状态机不依赖 Qt，也不看真实时钟。"""

from datetime import datetime, timedelta

from joapp.scheduler.timer import FocusTracker, Phase

T0 = datetime(2026, 8, 5, 9, 0)


def tick_minutes(tracker: FocusTracker, count: int, idle: float = 0.0) -> None:
    for i in range(1, count + 1):
        tracker.tick(idle, T0 + timedelta(minutes=i))


def test_active_input_accumulates_focus():
    tr = FocusTracker()
    tick_minutes(tr, 9)
    # 第一次 tick 没有基准时间，不计入 —— 9 次 tick = 8 分钟
    assert tr.phase is Phase.FOCUS
    assert tr.focus_minutes == 8.0


def test_going_idle_stops_accumulating_but_keeps_the_streak():
    tr = FocusTracker(idle_threshold_minutes=5)
    tick_minutes(tr, 6)
    banked = tr.focus_minutes

    tr.tick(30.0, T0 + timedelta(minutes=8))  # 离开了
    assert tr.phase is Phase.AWAY
    assert tr.focus_minutes == banked  # 没涨，也没清零


def test_short_absence_resumes_the_same_streak():
    tr = FocusTracker(idle_threshold_minutes=5, reset_after_away_minutes=20)
    tick_minutes(tr, 5)
    banked = tr.focus_minutes

    tr.tick(10.0, T0 + timedelta(minutes=8))  # 走开 3 分钟
    tr.tick(0.0, T0 + timedelta(minutes=9))  # 回来了
    assert tr.phase is Phase.FOCUS
    assert tr.focus_minutes > banked


def test_long_absence_resets_the_streak():
    tr = FocusTracker(idle_threshold_minutes=5, reset_after_away_minutes=20)
    tick_minutes(tr, 5)

    # 分几步走开 25 分钟，避免被大跳变过滤掉
    for i in range(6, 31, 5):
        tr.tick(60.0, T0 + timedelta(minutes=i))
    assert tr.phase is Phase.AWAY

    tr.tick(0.0, T0 + timedelta(minutes=27))
    assert tr.phase is Phase.FOCUS
    assert tr.focus_minutes == 1.0  # 从头开始，只算回来后的这 1 分钟


def test_clock_jumps_are_discarded():
    """合上笔记本三小时，不该算成专注了三小时。"""
    tr = FocusTracker()
    tick_minutes(tr, 3)
    banked = tr.focus_minutes

    tr.tick(0.0, T0 + timedelta(hours=3))
    assert tr.focus_minutes == banked


def test_break_pauses_focus_and_resets_it():
    tr = FocusTracker()
    tick_minutes(tr, 10)

    tr.start_break()
    assert tr.phase is Phase.BREAK
    assert tr.focus_minutes == 0.0

    tr.tick(0.0, T0 + timedelta(minutes=13))
    assert tr.phase is Phase.BREAK  # 休息期间输入不会把状态拽回 FOCUS
    assert tr.break_minutes > 0

    tr.end_break()
    assert tr.phase is Phase.FOCUS
    assert tr.break_minutes == 0.0


def test_snooze_pushes_the_next_break_back():
    tr = FocusTracker()
    tick_minutes(tr, 20)
    before = tr.focus_minutes

    tr.snooze(10)
    assert tr.focus_minutes == before - 10


def test_snooze_never_goes_negative():
    tr = FocusTracker()
    tick_minutes(tr, 3)
    tr.snooze(60)
    assert tr.focus_minutes == 0.0
