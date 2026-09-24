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


def test_daily_done_resets_next_day(tmp_path):
    store = make_store(tmp_path)
    todo = store.add("喝水", Scope.DAILY, MON)
    store.set_done(todo, True, MON)

    assert store.todos(Scope.DAILY, MON)[0].done is True
    tomorrow = store.todos(Scope.DAILY, MON + timedelta(days=1))
    assert titles(tomorrow) == ["喝水"]  # 还在
    assert tomorrow[0].done is False  # 但又是没做的


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
