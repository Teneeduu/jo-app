"""提醒进程的测试。

脚本拼装部分纯字符串，哪都能跑。起真进程的那几条只在 Windows 上跑，
并且都把间隔设得很长 / 不弹窗 —— 测试不会真的念出声或者弹框。
"""

import base64
import os
import subprocess
import sys
import textwrap
import time

import pytest

from joapp import reminder

windows_only = pytest.mark.skipif(os.name != "nt", reason="需要 Windows PowerShell")


def test_quotes_survive_powershell_literal():
    script = reminder.build_script("It's 喝水", "别'走'", 60)
    assert "'It''s 喝水'" in script
    assert "'别''走'''" in script


def test_encoded_command_round_trips_chinese():
    script = reminder.build_script("喝水时间到了", "休息下吧", 3600)
    cmd = reminder.command(script)
    assert cmd[-2] == "-EncodedCommand"
    assert base64.b64decode(cmd[-1]).decode("utf-16-le") == script


def test_interval_and_loop_are_baked_in():
    looped = reminder.build_script("a", "b", 3600)
    once = reminder.build_script("a", "b", 0, loop=False)
    assert "Start-Sleep -Seconds 3600" in looped and "while ($true)" in looped
    assert "Start-Sleep -Seconds 0" in once and "while ($false)" in once


def test_nothing_to_say_is_a_failure(tmp_path):
    r = reminder.Reminder(tmp_path / "r.log")
    status = r.start("", "", 60)
    assert status.state == "failed"
    assert r.pid is None


def wait_for(r, timeout=30):
    deadline = time.time() + timeout
    status = r.status()
    while status.state == "starting" and time.time() < deadline:
        time.sleep(0.3)
        status = r.status()
    return status


@windows_only
def test_starts_and_stops(tmp_path):
    r = reminder.Reminder(tmp_path / "r.log")
    r.start("测试", "", 600)  # 10 小时一次，测试期间不会出声
    status = wait_for(r)
    assert status.state == "running", status.detail
    proc = r._proc

    r.stop()
    assert proc.poll() is not None
    assert r.status().state == "off"


@windows_only
def test_script_error_is_reported_in_plain_text(tmp_path, monkeypatch):
    broken = reminder._SCRIPT.replace("System.Speech\n", "System.NoSuchAssembly\n")
    monkeypatch.setattr(reminder, "_SCRIPT", broken)
    r = reminder.Reminder(tmp_path / "r.log")
    r.start("测试", "", 600)
    status = wait_for(r)
    assert status.state == "failed"
    assert "NoSuchAssembly" in status.detail
    assert "CLIXML" not in status.detail


@windows_only
def test_child_dies_when_parent_is_killed(tmp_path):
    """应用被硬杀（任务管理器 / 崩溃）时，后台提醒也得跟着没 —— job object 的活。"""
    pid_file = tmp_path / "pid.txt"
    code = textwrap.dedent(
        f"""
        import os, sys, time
        sys.path.insert(0, {os.getcwd()!r})
        from joapp import reminder
        r = reminder.Reminder(r"{tmp_path / 'r.log'}")
        r.start("测试", "", 600)
        open(r"{pid_file}", "w").write(str(r.pid))
        time.sleep(60)
        """
    )
    parent = subprocess.Popen([sys.executable, "-c", code])
    deadline = time.time() + 20
    while not pid_file.exists() and time.time() < deadline:
        time.sleep(0.2)
    child = int(pid_file.read_text())
    assert _alive(child)

    parent.kill()  # TerminateProcess：不给 Python 任何收尾机会
    parent.wait()
    deadline = time.time() + 10
    while _alive(child) and time.time() < deadline:
        time.sleep(0.2)
    assert not _alive(child)


def _alive(pid: int) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
        capture_output=True,
        text=True,
    ).stdout
    return f'"{pid}"' in out


class _Running:
    pid = 1

    def poll(self):
        return None


@pytest.mark.parametrize(
    "line,warns",
    [
        ("jo-app-reminder-ready|Microsoft Huihui Desktop|zh-CN", False),
        ("jo-app-reminder-ready|Microsoft Zira Desktop|en-US", True),
        ("jo-app-reminder-ready", False),  # 旧格式 / 没报语音：不乱警告
    ],
)
def test_warns_when_no_chinese_voice(tmp_path, line, warns):
    """别的电脑可能只装了英文语音 —— 念中文会听不清，得在窗口里说出来。"""
    log = tmp_path / "r.log"
    log.write_text(line + "\n", encoding="utf-8")
    r = reminder.Reminder(log)
    r._proc, r.minutes = _Running(), 60
    status = r.status()
    assert status.state == "running"
    assert ("没有中文语音" in status.detail) is warns
