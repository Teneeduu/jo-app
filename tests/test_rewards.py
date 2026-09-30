"""奖励的测试：够线才发、每个周期只发一次、换周期重来。"""

from datetime import date, timedelta

import pytest

from joapp.core.models import Scope, reached
from joapp.core.store import Store

MON = date(2026, 9, 21)  # 周一


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "test.db")


def texts(rewards):
    return [r.text for r in rewards]


@pytest.mark.parametrize(
    "done,total,percent,expected",
    [
        (1, 2, 50, True),
        (1, 3, 50, False),
        (2, 3, 50, True),
        (1, 3, 33, True),  # 33.3% ≥ 33%
        (1, 3, 34, False),
        (3, 3, 100, True),
        (2, 3, 100, False),
        (0, 0, 1, False),  # 一件都没有，不算完成
    ],
)
def test_reached(done, total, percent, expected):
    assert reached(done, total, percent) is expected


def test_reward_fires_once_when_threshold_is_crossed(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY, MON)
    b = store.add("背单词", Scope.DAILY, MON)
    store.add_reward(Scope.DAILY, 50, "看一集剧")
    store.add_reward(Scope.DAILY, 100, "吃顿好的")

    assert store.claim_reached(Scope.DAILY, MON) == []  # 0/2

    store.set_done(a, True, MON)
    assert texts(store.claim_reached(Scope.DAILY, MON)) == ["看一集剧"]
    assert store.claim_reached(Scope.DAILY, MON) == []  # 不重复发

    store.set_done(b, True, MON)
    assert texts(store.claim_reached(Scope.DAILY, MON)) == ["吃顿好的"]


def test_jumping_past_several_thresholds_gives_all_of_them(tmp_path):
    store = make_store(tmp_path)
    a = store.add("打扫", Scope.WEEKLY, MON)
    store.add_reward(Scope.WEEKLY, 50, "奶茶")
    store.add_reward(Scope.WEEKLY, 100, "电影")
    store.set_done(a, True, MON)
    assert texts(store.claim_reached(Scope.WEEKLY, MON)) == ["奶茶", "电影"]


def test_unchecking_and_rechecking_does_not_pay_twice(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY, MON)
    store.add_reward(Scope.DAILY, 100, "看一集剧")
    store.set_done(a, True, MON)
    store.claim_reached(Scope.DAILY, MON)

    store.set_done(a, False, MON)
    store.set_done(a, True, MON)
    assert store.claim_reached(Scope.DAILY, MON) == []
    assert store.rewards(Scope.DAILY, MON)[0].earned is True


def test_rewards_reset_each_period(tmp_path):
    store = make_store(tmp_path)
    d = store.add("喝水", Scope.DAILY, MON)
    w = store.add("打扫", Scope.WEEKLY, MON)
    store.add_reward(Scope.DAILY, 100, "日奖")
    store.add_reward(Scope.WEEKLY, 100, "周奖")
    store.set_done(d, True, MON)
    store.set_done(w, True, MON)
    store.claim_reached(Scope.DAILY, MON)
    store.claim_reached(Scope.WEEKLY, MON)

    tue = MON + timedelta(days=1)
    assert store.rewards(Scope.DAILY, tue)[0].earned is True  # 过了零点不算新一轮
    assert store.rewards(Scope.WEEKLY, tue)[0].earned is True  # 还是这周

    store.reset_daily()  # 按了「重新开始」
    assert store.rewards(Scope.DAILY, tue)[0].earned is False
    assert store.rewards(Scope.WEEKLY, tue)[0].earned is True  # 每周的不受影响
    assert store.claim_reached(Scope.DAILY, tue) == []  # 任务也清了，还没够线
    store.set_done(d, True, tue)
    assert texts(store.claim_reached(Scope.DAILY, tue)) == ["日奖"]

    next_mon = MON + timedelta(days=7)
    assert store.rewards(Scope.WEEKLY, next_mon)[0].earned is False


def test_scopes_do_not_mix(tmp_path):
    """每天的完成度只看每天任务，当天任务做得再多也不算。"""
    store = make_store(tmp_path)
    store.add("喝水", Scope.DAILY, MON)
    t = store.add("交报告", Scope.TODAY, MON)
    store.add_reward(Scope.DAILY, 50, "看一集剧")
    store.set_done(t, True, MON)
    assert store.claim_reached(Scope.DAILY, MON) == []


def test_today_scope_cannot_have_rewards(tmp_path):
    with pytest.raises(ValueError):
        make_store(tmp_path).add_reward(Scope.TODAY, 50, "x")


def test_percent_is_clamped_and_list_is_sorted(tmp_path):
    store = make_store(tmp_path)
    store.add_reward(Scope.YEARLY, 150, "年")
    store.add_reward(Scope.DAILY, 100, "日100")
    store.add_reward(Scope.DAILY, 0, "日1")
    assert [(r.scope, r.percent) for r in store.rewards()] == [
        (Scope.DAILY, 1),
        (Scope.DAILY, 100),
        (Scope.YEARLY, 100),
    ]


def test_deleting_reward_drops_its_claims(tmp_path):
    store = make_store(tmp_path)
    a = store.add("喝水", Scope.DAILY, MON)
    r = store.add_reward(Scope.DAILY, 100, "看一集剧")
    store.set_done(a, True, MON)
    store.claim_reached(Scope.DAILY, MON)
    store.delete_reward(r.id)
    assert store.rewards() == []
    assert store.conn.execute("SELECT COUNT(*) FROM reward_claims").fetchone()[0] == 0
