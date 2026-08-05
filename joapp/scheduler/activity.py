"""空闲检测：距离上一次键鼠输入过了多久。

Windows 下用 GetLastInputInfo（系统级，不需要装钩子、不读按键内容）。
其他平台没有等价的免权限接口，直接返回 0 —— 相当于「一直在用」，
应用退化成纯计时的番茄钟，功能不受影响。
"""

from __future__ import annotations

import ctypes
import os

_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]


def idle_seconds() -> float:
    """距上次键鼠输入的秒数。非 Windows 恒为 0。"""
    if not _IS_WINDOWS:
        return 0.0
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    tick = ctypes.windll.kernel32.GetTickCount()
    # GetTickCount 49.7 天回绕一次，取模消掉负数
    return ((tick - info.dwTime) % (2**32)) / 1000.0


def idle_minutes() -> float:
    return idle_seconds() / 60.0
