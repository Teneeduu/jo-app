"""Store 的测试。用临时文件当库，不碰真实数据目录。"""

import sqlite3
from datetime import date, timedelta

from joapp.core.models import Scope, period_key
from joapp.core.store import Store

MON = date(2026, 9, 21)  # 周一


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "test.db")


def titles(todos):
    return [t.title for t in todos]


def test_add_and_read_by_scope(tmp_path):
    store = make_store(tmp_path)
    store.add("喝水", Scope.DAILY, MON)
    store.add("交报告", Scope.TODAY, MON)
    store.add("打扫", Scope.WEEKLY, MON)
    store.add("读 20 本书", Scope.YEARLY, MON)

    assert titles(store.todos(Scope.DAILY, MON)) == ["喝水"]
    assert titles(store.todos(Scope.TODAY, MON)) == ["交报告"]
    assert titles(store.todos(Scope.WEEKLY, MON)) == ["打扫"]
    assert titles(store.todos(Scope.YEARLY, MON)) == ["读 20 本书"]


def test_title_is_trimmed(tmp_path):
    store = make_store(tmp_path)
    assert store.add("  跑步 \n", Scope.DAILY).title == "跑步"


def test_daily_done_does_not_follow_the_calendar(tmp_path):
    """每天任务不按日期清零 —— 过了零点还是做完的，等你自己按「重新开始」。"""
    store = make_store(tmp_path)
    todo = store.add("喝水", Scope.DAILY, MON)
    store.set_done(todo, True, MON)

    later = store.todos(Scope.DAILY, MON + timedelta(days=3))
    assert titles(later) == ["喝水"]
    assert later[0].done is True


def test_reset_daily_starts_a_new_round(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY, MON)
    b = store.add("背单词", Scope.DAILY, MON)
    w = store.add("打扫", Scope.WEEKLY, MON)
    t = store.add("交报告", Scope.TODAY, MON)
    for todo in (a, b, w, t):
        store.set_done(todo, True, MON)
    before = store.round_started(Scope.DAILY)

    store.reset(Scope.DAILY)

    assert [x.done for x in store.todos(Scope.DAILY, MON)] == [False, False]
    assert store.todos(Scope.WEEKLY, MON)[0].done is True  # 只动每天任务
    assert store.todos(Scope.TODAY, MON)[0].done is True
    assert store.round_started(Scope.DAILY) >= before

    store.set_done(a, True, MON)  # 新一轮照常勾
    assert [x.done for x in store.todos(Scope.DAILY, MON)] == [True, False]


def test_reset_twice_in_a_row_still_starts_fresh(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY, MON)
    store.reset(Scope.DAILY)
    store.set_done(a, True, MON)
    store.reset(Scope.DAILY)
    assert store.todos(Scope.DAILY, MON)[0].done is False


def test_round_survives_reopening(tmp_path):
    path = tmp_path / "test.db"
    store = Store(path)
    a = store.add("喝水", Scope.DAILY, MON)
    store.reset(Scope.DAILY)
    store.set_done(a, True, MON)
    store.close()

    assert Store(path).todos(Scope.DAILY, MON)[0].done is True


def test_upgrade_keeps_todays_daily_checks(tmp_path):
    """旧版本按日期记的「今天勾掉了」，升级后第一轮就是今天，所以还算数。"""
    path = tmp_path / "old.db"
    store = Store(path)
    a = store.add("喝水", Scope.DAILY)
    store.conn.execute(
        "INSERT INTO todo_done (todo_id, period, done_at) VALUES (?, ?, ?)",
        (a.id, date.today().isoformat(), "2026-09-29T08:00:00"),
    )
    store.conn.execute("DELETE FROM meta WHERE key LIKE 'daily_round%'")
    store.conn.commit()
    store.close()

    assert Store(path).todos(Scope.DAILY)[0].done is True


def test_weekly_done_lasts_the_iso_week(tmp_path):
    store = make_store(tmp_path)
    todo = store.add("打扫", Scope.WEEKLY, MON)
    store.set_done(todo, True, MON)

    assert store.todos(Scope.WEEKLY, MON + timedelta(days=6))[0].done is True  # 周日
    assert store.todos(Scope.WEEKLY, MON + timedelta(days=7))[0].done is False  # 下周一


def test_yearly_done_lasts_the_year(tmp_path):
    store = make_store(tmp_path)
    todo = store.add("体检", Scope.YEARLY, MON)
    store.set_done(todo, True, MON)

    assert store.todos(Scope.YEARLY, date(2026, 12, 31))[0].done is True
    assert store.todos(Scope.YEARLY, date(2027, 1, 1))[0].done is False


def test_unchecking_undoes(tmp_path):
    store = make_store(tmp_path)
    todo = store.add("喝水", Scope.DAILY, MON)
    store.set_done(todo, True, MON)
    store.set_done(todo, True, MON)  # 重复勾不报错
    store.set_done(todo, False, MON)
    assert store.todos(Scope.DAILY, MON)[0].done is False


def test_unfinished_today_task_carries_over(tmp_path):
    """当天任务没做完就一直挂着，并且标出拖了几天。"""
    store = make_store(tmp_path)
    store.add("交报告", Scope.TODAY, MON)
    later = MON + timedelta(days=3)

    todos = store.todos(Scope.TODAY, later)
    assert titles(todos) == ["交报告"]
    assert todos[0].overdue_days(later) == 3


def test_finished_today_task_disappears_next_day(tmp_path):
    store = make_store(tmp_path)
    todo = store.add("交报告", Scope.TODAY, MON)
    store.set_done(todo, True, MON)

    assert store.todos(Scope.TODAY, MON)[0].done is True  # 当天还看得到，划掉的
    assert store.todos(Scope.TODAY, MON + timedelta(days=1)) == []


def test_late_today_task_done_on_a_later_day(tmp_path):
    """拖了几天才做完：勾掉那一刻起就算完成，不会还挂在清单上。"""
    store = make_store(tmp_path)
    todo = store.add("交报告", Scope.TODAY, MON)
    later = MON + timedelta(days=2)
    store.set_done(todo, True, later)

    assert store.todos(Scope.TODAY, later) == []


def test_delete_removes_task_and_its_history(tmp_path):
    store = make_store(tmp_path)
    todo = store.add("喝水", Scope.DAILY, MON)
    store.set_done(todo, True, MON)
    store.delete(todo.id)

    assert store.todos(Scope.DAILY, MON) == []
    left = store.conn.execute("SELECT COUNT(*) FROM todo_done").fetchone()[0]
    assert left == 0


def test_period_keys():
    assert period_key(Scope.DAILY, MON) == "2026-09-21"
    assert period_key(Scope.DAILY, MON, daily_round="round-x") == "round-x"
    assert period_key(Scope.WEEKLY, MON) == "2026-W39"
    assert period_key(Scope.YEARLY, MON) == "2026"
    assert period_key(Scope.TODAY, MON + timedelta(days=5), MON) == "2026-09-21"


def test_legacy_open_tasks_are_imported_once(tmp_path):
    """旧版本的 tasks 表：没做完的搬成当天任务，做完 / 丢弃的不搬，只搬一次。"""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, day TEXT,
            status TEXT, estimate_minutes INTEGER, created_at TEXT);
        INSERT INTO tasks (title, day, status, created_at) VALUES
            ('没做完的', '2026-09-20', 'todo', '2026-09-20T08:00:00'),
            ('做完了的', '2026-09-20', 'done', '2026-09-20T08:00:00'),
            ('顺延走的', '2026-09-20', 'dropped', '2026-09-20T08:00:00');
        """
    )
    conn.commit()
    conn.close()

    Store(path).close()
    store = Store(path)  # 再开一次不能重复搬
    todos = store.todos(Scope.TODAY, MON)
    assert titles(todos) == ["没做完的"]
    assert todos[0].overdue_days(MON) == 1


# ---------- 每周 / 每年手动重来 ----------


def test_weekly_reset_mid_week_and_calendar_still_works(tmp_path):
    store = make_store(tmp_path)
    w = store.add("打扫", Scope.WEEKLY, MON)
    d = store.add("喝水", Scope.DAILY, MON)
    store.set_done(w, True, MON)
    store.set_done(d, True, MON)
    assert store.round_started(Scope.WEEKLY, MON) is None  # 还没手动重来过

    wed = MON + timedelta(days=2)
    store.reset(Scope.WEEKLY, wed)
    assert store.todos(Scope.WEEKLY, wed)[0].done is False
    assert store.todos(Scope.DAILY, wed)[0].done is True  # 别的分组不动
    assert store.round_started(Scope.WEEKLY, wed) is not None

    store.set_done(w, True, wed)
    store.reset(Scope.WEEKLY, wed)  # 同一周再按一次也有效
    assert store.todos(Scope.WEEKLY, wed)[0].done is False

    store.set_done(w, True, wed)
    next_mon = MON + timedelta(days=7)  # 到下周：日历照常重置，手动的后缀不再生效
    assert store.todos(Scope.WEEKLY, next_mon)[0].done is False
    assert store.round_started(Scope.WEEKLY, next_mon) is None


def test_yearly_reset_survives_reopening(tmp_path):
    path = tmp_path / "test.db"
    store = Store(path)
    y = store.add("体检", Scope.YEARLY, MON)
    store.set_done(y, True, MON)
    store.reset(Scope.YEARLY, MON)
    store.close()

    store = Store(path)
    assert store.todos(Scope.YEARLY, MON)[0].done is False
    store.set_done(y, True, MON)
    assert store.todos(Scope.YEARLY, date(2026, 12, 31))[0].done is True


def test_today_scope_has_no_rounds(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        make_store(tmp_path).reset(Scope.TODAY)


# ---------- 排序 ----------


def test_move_up_and_down(tmp_path):
    store = make_store(tmp_path)
    a, b, c = (store.add(x, Scope.DAILY, MON) for x in "abc")
    assert titles(store.todos(Scope.DAILY, MON)) == ["a", "b", "c"]

    assert store.move(c, -1, MON) is True
    assert titles(store.todos(Scope.DAILY, MON)) == ["a", "c", "b"]
    assert store.move(a, +1, MON) is True
    assert titles(store.todos(Scope.DAILY, MON)) == ["c", "a", "b"]

    assert store.move(c, -1, MON) is False  # 已经在最上面
    assert store.move(b, +1, MON) is False  # 已经在最下面
    assert titles(store.todos(Scope.DAILY, MON)) == ["c", "a", "b"]


def test_new_task_goes_last_and_groups_are_independent(tmp_path):
    store = make_store(tmp_path)
    a, b = store.add("a", Scope.DAILY, MON), store.add("b", Scope.DAILY, MON)
    store.add("w", Scope.WEEKLY, MON)
    store.move(b, -1, MON)
    store.add("c", Scope.DAILY, MON)
    assert titles(store.todos(Scope.DAILY, MON)) == ["b", "a", "c"]
    assert titles(store.todos(Scope.WEEKLY, MON)) == ["w"]


def test_move_skips_hidden_today_tasks(tmp_path):
    """当天分组里藏着以前做完的任务；上移一位要越过它们，不然按了没反应。"""
    store = make_store(tmp_path)
    old = store.add("昨天做完的", Scope.TODAY, MON - timedelta(days=1))
    store.set_done(old, True, MON - timedelta(days=1))
    a = store.add("a", Scope.TODAY, MON)
    store.add("b", Scope.TODAY, MON)
    b = store.todos(Scope.TODAY, MON)[1]
    assert titles(store.todos(Scope.TODAY, MON)) == ["a", "b"]
    assert store.move(b, -1, MON) is True
    assert titles(store.todos(Scope.TODAY, MON)) == ["b", "a"]
    assert store.move(a, -5, MON) is False


def test_order_survives_reopening_and_old_db_gets_positions(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            scope TEXT NOT NULL, day TEXT NOT NULL, created_at TEXT NOT NULL);
        INSERT INTO todos (title, scope, day, created_at) VALUES
            ('a', 'daily', '2026-09-21', '2026-09-21T08:00:00'),
            ('b', 'daily', '2026-09-21', '2026-09-21T08:00:00');
        """
    )
    conn.commit()
    conn.close()

    store = Store(path)  # 没有 position 列的旧库：补上，保持原顺序
    assert titles(store.todos(Scope.DAILY, MON)) == ["a", "b"]
    store.move(store.todos(Scope.DAILY, MON)[1], -1, MON)
    store.close()
    assert titles(Store(path).todos(Scope.DAILY, MON)) == ["b", "a"]
