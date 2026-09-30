"""活动记录：格子排布、颜色分档、连续天数，以及记录本身的增删。"""

import sqlite3
from datetime import date, datetime, timedelta

from joapp.core import stats
from joapp.core.models import Scope
from joapp.core.store import Store

MON = date(2026, 9, 21)  # 周一


def at(d: date, hour: int = 10) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(hour=hour)


# ---------- 纯计算 ----------


def test_weeks_start_on_monday_and_blank_outside_range():
    cols = stats.weeks(date(2026, 9, 23), date(2026, 9, 29))  # 周三 ~ 下周二
    assert len(cols) == 2
    assert cols[0][:2] == [None, None]  # 周一、周二不在范围里
    assert cols[0][2] == date(2026, 9, 23)
    assert cols[1][1] == date(2026, 9, 29)
    assert cols[1][2:] == [None] * 5


def test_last_year_is_53_columns_ending_today():
    start, end = stats.last_year(date(2026, 9, 29))
    cols = stats.weeks(start, end)
    assert len(cols) == 53
    assert start.weekday() == 0
    assert end == date(2026, 9, 29)


def test_year_range_stops_at_today_for_this_year():
    today = date(2026, 9, 29)
    assert stats.year_range(2026, today) == (date(2026, 1, 1), today)
    assert stats.year_range(2025, today) == (date(2025, 1, 1), date(2025, 12, 31))


def test_levels():
    assert stats.level(0, 10) == 0
    assert stats.level(1, 10) == 1
    assert stats.level(10, 10) == 4  # 最忙那天总是最深
    assert stats.level(6, 10) == 3
    assert stats.level(1, 1) == 4


def test_streaks():
    today = date(2026, 9, 29)
    days = {today - timedelta(days=i) for i in (0, 1, 2)} | {
        date(2026, 9, 1) + timedelta(days=i) for i in range(5)
    }
    assert stats.streaks(days, today) == (3, 5)


def test_streak_not_broken_yet_if_today_is_empty():
    today = date(2026, 9, 29)
    days = {today - timedelta(days=1), today - timedelta(days=2)}
    assert stats.streaks(days, today) == (2, 2)
    assert stats.streaks({today - timedelta(days=3)}, today) == (0, 1)
    assert stats.streaks(set(), today) == (0, 0)


# ---------- 记录 ----------


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "test.db")


def test_checking_records_and_unchecking_takes_it_back(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY, MON)
    b = store.add("交报告", Scope.TODAY, MON)
    store.set_done(a, True, MON, at=at(MON, 9))
    store.set_done(a, True, MON, at=at(MON, 11))  # 重复勾不重复记
    store.set_done(b, True, MON, at=at(MON, 15))

    day = store.activity_on(MON)
    assert [(x.kind, x.title, x.scope, x.at.hour) for x in day] == [
        ("task", "喝水", Scope.DAILY, 9),
        ("task", "交报告", Scope.TODAY, 15),
    ]
    assert store.activity_counts(MON, MON) == {MON: 2}

    store.set_done(b, False, MON)  # 点错了，撤回
    assert [x.title for x in store.activity_on(MON)] == ["喝水"]


def test_history_survives_deleting_the_task(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY, MON)
    store.set_done(a, True, MON, at=at(MON))
    store.delete(a.id)
    assert [x.title for x in store.activity_on(MON)] == ["喝水"]


def test_same_daily_task_across_rounds_counts_each_time(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY, MON)
    store.set_done(a, True, MON, at=at(MON))
    store.reset_daily()
    store.set_done(a, True, MON, at=at(MON + timedelta(days=1)))
    store.set_done(a, False, MON)  # 只撤这一轮的
    assert store.activity_counts(MON, MON + timedelta(days=1)) == {MON: 1}


def test_rewards_show_in_the_day_but_not_in_counts(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY)
    store.add_reward(Scope.DAILY, 100, "看一集剧")
    store.set_done(a, True)
    store.claim_reached(Scope.DAILY)

    today = date.today()
    kinds = [(x.kind, x.title) for x in store.activity_on(today)]
    assert kinds == [("task", "喝水"), ("reward", "看一集剧")]
    assert store.activity_counts(today, today) == {today: 1}


def test_counts_respect_the_range_and_years_list(tmp_path):
    store = make_store(tmp_path)
    old = date(2024, 12, 31)
    for d in (old, MON, MON, MON + timedelta(days=1)):
        t = store.add("x", Scope.TODAY, d)
        store.set_done(t, True, d, at=at(d))

    assert store.activity_counts(MON, MON) == {MON: 2}
    assert store.activity_counts(date(2026, 1, 1), date(2026, 12, 31)) == {
        MON: 2,
        MON + timedelta(days=1): 1,
    }
    assert store.activity_days() == {old, MON, MON + timedelta(days=1)}
    assert store.activity_years(MON) == [2026, 2024]


def test_backfill_from_existing_records_and_oldest_version(tmp_path):
    """升级到有活动记录的版本时，之前勾掉的、拿到的、最早那版做完的都补进来。"""
    path = tmp_path / "old.db"
    store = Store(path)
    a = store.add("喝水", Scope.DAILY, MON)
    r = store.add_reward(Scope.DAILY, 100, "看一集剧")
    store.conn.executescript(
        f"""
        INSERT INTO todo_done (todo_id, period, done_at)
            VALUES ({a.id}, 'p', '2026-09-20T08:00:00');
        INSERT INTO reward_claims (reward_id, period, claimed_at)
            VALUES ({r.id}, 'p', '2026-09-20T08:01:00');
        CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, day TEXT, status TEXT,
            created_at TEXT, done_at TEXT);
        INSERT INTO tasks (title, day, status, created_at, done_at) VALUES
            ('旧版做完的', '2026-09-10', 'done', '2026-09-10T08:00:00', '2026-09-10T20:00:00'),
            ('旧版没做的', '2026-09-10', 'todo', '2026-09-10T08:00:00', NULL);
        DELETE FROM activity;
        DELETE FROM meta WHERE key = 'activity_backfilled';
        """
    )
    store.close()

    store = Store(path)
    Store(path).close()  # 再开一次不能重复补
    assert [(x.kind, x.title) for x in store.activity_on(date(2026, 9, 20))] == [
        ("task", "喝水"),
        ("reward", "看一集剧"),
    ]
    old = store.activity_on(date(2026, 9, 10))
    assert [(x.title, x.scope) for x in old] == [("旧版做完的", None)]
    n = sqlite3.connect(path).execute("SELECT COUNT(*) FROM activity").fetchone()[0]
    assert n == 3
