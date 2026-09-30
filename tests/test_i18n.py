"""界面语言。最重要的一条：源码里每个 t("...") 都得有英文，占位符还得对得上。"""

import ast
import string
from datetime import date, datetime
from pathlib import Path

import pytest

from joapp import i18n, reminder
from joapp.core.models import Scope

SRC = Path(__file__).resolve().parents[1] / "joapp"


@pytest.fixture(autouse=True)
def back_to_chinese():
    yield
    i18n.set_language("zh")


def _keys_in_source() -> dict[str, str]:
    """{中文 key: 出现在哪个文件}。用 AST 找，跨行拼接的字符串也认得。"""
    found = {}
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            first = node.args[0]
            if name == "t" and isinstance(first, ast.Constant) and isinstance(first.value, str):
                found[first.value] = path.name
    return found


def _placeholders(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_ui_string_has_english():
    keys = _keys_in_source()
    keys.update({label: "models.py" for label in ("每天", "当天", "每周", "每年")})
    assert len(keys) > 50  # 真的扫到了东西
    missing = {k: f for k, f in keys.items() if k not in i18n.EN}
    assert missing == {}, "这些 t() 还没有英文：\n" + "\n".join(f"{f}: {k!r}" for k, f in missing.items())


def test_placeholders_match():
    wrong = {
        zh: en
        for zh, en in i18n.EN.items()
        if _placeholders(zh) != _placeholders(en)
    }
    assert wrong == {}


def test_no_stale_english_entries():
    used = set(_keys_in_source()) | {"每天", "当天", "每周", "每年"}
    assert set(i18n.EN) - used == set()


def test_switching_changes_labels():
    assert Scope.DAILY.label == "每天"
    i18n.set_language("en")
    assert Scope.DAILY.label == "Daily"
    assert i18n.t("拖了 {n} 天", n=3) == "3d overdue"
    i18n.set_language("zh")
    assert i18n.t("拖了 {n} 天", n=3) == "拖了 3 天"


def test_unknown_language_falls_back_to_chinese():
    i18n.set_language("fr")
    assert i18n.language() == "zh"


def test_resolve():
    assert i18n.resolve("en") == "en"
    assert i18n.resolve("zh") == "zh"
    assert i18n.resolve("auto") in i18n.LANGUAGES


def test_dates():
    d = date(2026, 9, 29)
    assert i18n.date_line(d) == "9月29日 周二 · 第40周"
    assert i18n.month_short(1) == "1月"
    assert i18n.round_since(datetime(2026, 9, 29, 8, 5)) == "9/29 08:05 起"
    i18n.set_language("en")
    assert i18n.date_line(d) == "Tue, Sep 29 · Week 40"
    assert i18n.month_short(1) == "Jan"
    assert i18n.weekday_short(0) == "Mon"
    assert i18n.round_since(datetime(2026, 9, 29, 8, 5)) == "since 9/29 08:05"


def test_default_reminder_text_follows_language_custom_text_does_not():
    i18n.set_language("en")
    chinese_default = i18n.DEFAULT_VOICE["zh"]
    assert i18n.reminder_text(chinese_default, i18n.DEFAULT_VOICE) == i18n.DEFAULT_VOICE["en"]
    assert i18n.reminder_text("我自己写的", i18n.DEFAULT_VOICE) == "我自己写的"
    assert i18n.reminder_text("", i18n.DEFAULT_POPUP) == ""  # 空 = 不弹，别给补回来


def test_script_uses_title_and_voice_language():
    script = reminder.build_script("Hi", "Break", 60, title="Reminder", culture="en")
    assert "MessageBox]::Show($owner, $popup, 'Reminder')" in script
    assert "-like 'en*'" in script


class _Running:
    pid = 1

    def poll(self):
        return None


def test_english_mode_warns_about_missing_english_voice(tmp_path):
    i18n.set_language("en")
    log = tmp_path / "r.log"
    log.write_text("jo-app-reminder-ready|Microsoft Huihui Desktop|zh-CN\n", encoding="utf-8")
    r = reminder.Reminder(log)
    r._proc, r.minutes, r.culture = _Running(), 60, "en"
    detail = r.status().detail
    assert detail.startswith("every 60 min")
    assert "no English voice" in detail
