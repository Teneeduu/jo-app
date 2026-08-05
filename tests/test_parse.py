"""离线解析器的测试。

这是「没连 Claude 时的契约」—— 界面上写明的格式，这里必须条条能解析对，
否则那句提示就是在骗人。
"""

from joapp.agent.parse import DEFAULT_MINUTES, parse_plan, used_fallback_split


def titles(raw: str) -> list[str]:
    return [t.title for t in parse_plan(raw)]


def minutes(raw: str) -> list[int]:
    return [t.minutes for t in parse_plan(raw)]


# --- 推荐写法：一行一件事 ---


def test_one_task_per_line():
    assert titles("写完季度报告\n读书第 3-4 章\n跑步 5 公里") == [
        "写完季度报告",
        "读书第 3-4 章",
        "跑步 5 公里",
    ]


def test_blank_lines_are_ignored():
    assert titles("写报告\n\n\n跑步\n") == ["写报告", "跑步"]


def test_commas_inside_a_line_are_kept():
    """多行模式下不再二次切分 —— 行就是行。"""
    assert titles("写报告，包括图表和结论\n跑步") == ["写报告，包括图表和结论", "跑步"]


# --- 时长 ---


def test_minutes_in_various_units():
    raw = "写报告 45分钟\n看书 45分\n跑步 1小时\n复盘 1.5h\n回邮件 30min"
    assert minutes(raw) == [45, 45, 60, 90, 30]


def test_duration_is_stripped_from_the_title():
    assert titles("写完季度报告 2小时") == ["写完季度报告"]
    assert titles("读书第 3-4 章（50分钟）") == ["读书第 3-4 章"]


def test_missing_duration_falls_back_to_default():
    tasks = parse_plan("写报告")
    assert tasks[0].minutes == DEFAULT_MINUTES
    assert tasks[0].explicit_minutes is False


def test_explicit_flag_marks_user_supplied_durations():
    tasks = parse_plan("写报告 2小时\n跑步")
    assert [t.explicit_minutes for t in tasks] == [True, False]


def test_durations_are_clamped():
    assert minutes("马拉松 99小时") == [240]
    assert minutes("发个呆 1分钟") == [5]


def test_a_bare_number_with_m_is_not_a_duration():
    """「跑步 5000m」是米，不是 5000 分钟。"""
    tasks = parse_plan("跑步 5000m")
    assert tasks[0].title == "跑步 5000m"
    assert tasks[0].explicit_minutes is False


# --- 项目符号 / 序号 ---


def test_bullets_and_numbering_are_stripped():
    assert titles("- 写报告\n* 跑步\n• 看书") == ["写报告", "跑步", "看书"]
    assert titles("1. 写报告\n2、跑步\n3) 看书") == ["写报告", "跑步", "看书"]


def test_bullet_plus_duration_together():
    tasks = parse_plan("- 写完季度报告 2小时")
    assert tasks[0].title == "写完季度报告"
    assert tasks[0].minutes == 120


# --- 单行兜底 ---


def test_single_line_falls_back_to_punctuation_split():
    assert titles("上午写完季度报告，下午看两章书，晚上跑个步") == [
        "上午写完季度报告",
        "下午看两章书",
        "晚上跑个步",
    ]


def test_connectives_split_a_single_line():
    assert titles("先写报告然后跑步") == ["先写报告", "跑步"]


def test_zai_is_not_a_separator():
    """「再战」「再看一遍」里的「再」不是分隔符，切了就毁词。"""
    assert titles("把方案再看一遍") == ["把方案再看一遍"]


def test_fallback_detection():
    assert used_fallback_split("写报告，跑步") is True
    assert used_fallback_split("写报告\n跑步") is False


# --- 边界 ---


def test_empty_input_yields_nothing():
    assert parse_plan("") == []
    assert parse_plan("   \n\n  ") == []


def test_too_short_fragments_are_dropped():
    assert titles("好\n写完季度报告") == ["写完季度报告"]
