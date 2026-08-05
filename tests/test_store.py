"""Store 的测试。用临时文件当库，不碰真实数据目录。"""

from datetime import date, timedelta

from joapp.core.models import Goal, Task, TaskStatus
from joapp.core.store import Store


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "test.db")


def test_add_and_read_tasks(tmp_path):
    store = make_store(tmp_path)
    task = store.add_task(Task(title="写周报", estimate_minutes=45))
    assert task.id is not None

    today = store.tasks_for()
    assert len(today) == 1
    assert today[0].title == "写周报"
    assert today[0].estimate_minutes == 45


def test_tasks_are_scoped_to_a_day(tmp_path):
    store = make_store(tmp_path)
    store.add_task(Task(title="今天的"))
    store.add_task(Task(title="明天的", day=date.today() + timedelta(days=1)))

    assert [t.title for t in store.tasks_for()] == ["今天的"]
    assert len(store.tasks_for(date.today() + timedelta(days=1))) == 1


def test_completing_a_task_stamps_done_at(tmp_path):
    store = make_store(tmp_path)
    task = store.add_task(Task(title="跑步"))
    store.set_task_status(task.id, TaskStatus.DONE)

    reloaded = store.tasks_for()[0]
    assert reloaded.status is TaskStatus.DONE
    assert reloaded.done_at is not None
    assert not reloaded.is_open


def test_planned_today_reflects_task_presence(tmp_path):
    store = make_store(tmp_path)
    assert store.planned_today() is False
    store.add_task(Task(title="随便什么"))
    assert store.planned_today() is True


def test_session_time_lands_on_the_task(tmp_path):
    store = make_store(tmp_path)
    task = store.add_task(Task(title="看书"))
    session = store.start_session(task.id)
    store.end_session(session)

    assert store.focus_minutes_today() >= 0
    assert store.tasks_for()[0].spent_minutes >= 0


def test_goal_progress_never_goes_negative(tmp_path):
    store = make_store(tmp_path)
    goal = store.add_goal(Goal(title="读完 300 页", target=300, progress=10))
    store.bump_goal(goal.id, -50)
    assert store.goals()[0].progress == 0


def test_goals_sort_by_deadline(tmp_path):
    store = make_store(tmp_path)
    store.add_goal(Goal(title="没期限"))
    store.add_goal(Goal(title="下周", deadline=date.today() + timedelta(days=7)))
    store.add_goal(Goal(title="明天", deadline=date.today() + timedelta(days=1)))

    assert [g.title for g in store.goals()] == ["明天", "下周", "没期限"]


def test_nudge_log_remembers_the_last_time(tmp_path):
    store = make_store(tmp_path)
    assert store.last_nudge_at("break") is None
    store.log_nudge("break", "歇会儿", "站起来走走", "rules")
    assert store.last_nudge_at("break") is not None
