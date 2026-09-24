"""定时提醒：后台一个隐藏的 PowerShell，每隔 N 分钟念一句话、弹一个框。

为什么不用 `Start-Process powershell -WindowStyle Hidden ...`：
Start-Process 起的进程跟我们断了关系，应用退出后它还在后台一小时念一次，
只能去任务管理器里找。这里改成自己 Popen，并且把子进程放进一个
Windows Job Object（KILL_ON_JOB_CLOSE）—— 应用正常退出时主动杀；
应用崩溃、被任务管理器结束时，系统回收 job 句柄也会顺带把它杀掉。

脚本用 -EncodedCommand（UTF-16LE base64）传进去，中文和引号都不用转义，
也不受控制台代码页影响。
"""

from __future__ import annotations

import base64
import ctypes
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"
READY_MARK = "jo-app-reminder-ready"

_SCRIPT = r"""
# 输出重定向到日志文件，默认会按控制台代码页（936）写，报错读回来是乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# 出错时自己写一行人话进日志。stderr 那条路 PowerShell 会写成 CLIXML，没法看
trap {{
    [Console]::Out.WriteLine('ERROR: ' + $_.Exception.Message)
    [Console]::Out.Flush()
    exit 1
}}
Add-Type -AssemblyName System.Speech
Add-Type -AssemblyName System.Windows.Forms
$voice = {voice}
$popup = {popup}
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
# 默认语音可能是英文的（Zira），念中文会变成乱读或者没声音 —— 有中文语音就换上
$zh = $s.GetInstalledVoices() | Where-Object {{ $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh*' }} | Select-Object -First 1
if ($zh) {{ $s.SelectVoice($zh.VoiceInfo.Name) }}
[Console]::Out.WriteLine('{ready}')
[Console]::Out.Flush()
do {{
    Start-Sleep -Seconds {seconds}
    if ($voice) {{ $s.SpeakAsync($voice) | Out-Null }}
    if ($popup) {{
        # 隐形的置顶窗口当 owner，弹框才会盖在别的窗口上面
        $owner = New-Object System.Windows.Forms.Form -Property @{{ TopMost = $true; ShowInTaskbar = $false }}
        [System.Windows.Forms.MessageBox]::Show($owner, $popup, '提示') | Out-Null
        $owner.Dispose()
    }}
    while ($s.State -eq 'Speaking') {{ Start-Sleep -Milliseconds 200 }}
}} while ({loop})
"""


def _ps_quote(text: str) -> str:
    """PowerShell 单引号字面量：里面只有 ' 需要写成 ''。"""
    return "'" + text.replace("'", "''") + "'"


def build_script(voice: str, popup: str, seconds: int, loop: bool = True) -> str:
    return _SCRIPT.format(
        voice=_ps_quote(voice),
        popup=_ps_quote(popup),
        seconds=max(0, int(seconds)),
        ready=READY_MARK,
        loop="$true" if loop else "$false",
    )


def encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def command(script: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encode(script),
    ]


# ---------- Job Object：父进程没了，子进程跟着没 ----------


class _KillOnCloseJob:
    """持有一个 job 句柄。句柄关掉（包括进程崩溃时由系统关掉）→ 里面的进程全被杀。"""

    def __init__(self) -> None:
        self.handle = None
        if not _IS_WINDOWS:
            return
        from ctypes import wintypes

        class BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class EXTENDED(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC),
                ("IoInfo", IO),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
        ]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._k32 = k32

        handle = k32.CreateJobObjectW(None, None)
        if not handle:
            log.warning("CreateJobObject 失败: %s", ctypes.get_last_error())
            return
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(
            handle, 9, ctypes.byref(info), ctypes.sizeof(info)  # 9 = ExtendedLimit
        ):
            log.warning("SetInformationJobObject 失败: %s", ctypes.get_last_error())
            k32.CloseHandle(handle)
            return
        self.handle = handle

    def adopt(self, proc: subprocess.Popen) -> bool:
        if not self.handle:
            return False
        ok = self._k32.AssignProcessToJobObject(self.handle, int(proc._handle))
        if not ok:
            log.warning("AssignProcessToJobObject 失败: %s", ctypes.get_last_error())
        return bool(ok)


# ---------- 对外接口 ----------


@dataclass
class Status:
    state: str  # off | starting | running | failed
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.state in ("starting", "running")


class Reminder:
    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self._job = _KillOnCloseJob()
        self._proc: subprocess.Popen | None = None
        self._one_shots: list[subprocess.Popen] = []
        self.minutes = 0
        self._failure = ""

    # --- 生命周期 ---

    def start(self, voice: str, popup: str, minutes: int) -> Status:
        self.stop()
        self._failure = ""
        if not _IS_WINDOWS:
            self._failure = "只支持 Windows"
            return self.status()
        if not (voice or popup):
            self._failure = "念的话和弹窗文字都是空的，没什么可提醒的"
            return self.status()
        self.minutes = max(1, int(minutes))
        script = build_script(voice, popup, self.minutes * 60)
        try:
            self._proc = self._spawn(script, self.log_path)
        except OSError as e:
            self._failure = f"启动 PowerShell 失败：{e}"
            self._proc = None
        else:
            log.info("提醒进程已启动 pid=%s，每 %s 分钟", self._proc.pid, self.minutes)
        return self.status()

    def fire_now(self, voice: str, popup: str) -> None:
        """立刻来一次（试听用）。同样挂在 job 上，退出时一起收走。"""
        if not _IS_WINDOWS or not (voice or popup):
            return
        self._one_shots = [p for p in self._one_shots if p.poll() is None]
        script = build_script(voice, popup, 0, loop=False)
        self._one_shots.append(
            self._spawn(script, self.log_path.with_name("reminder-test.log"))
        )

    def stop(self) -> None:
        for proc in [self._proc, *self._one_shots]:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._proc = None
        self._one_shots = []

    def _spawn(self, script: str, log_path: Path) -> subprocess.Popen:
        with open(log_path, "w", encoding="utf-8") as out:
            proc = subprocess.Popen(
                command(script),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.DEVNULL,  # 报错由脚本里的 trap 写进 stdout
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        self._job.adopt(proc)
        return proc

    # --- 状态 ---

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    def status(self) -> Status:
        if self._failure:
            return Status("failed", self._failure)
        if self._proc is None:
            return Status("off", "")
        output = self._read_log()
        code = self._proc.poll()
        if code is not None:
            tail = _last_lines(output.replace(READY_MARK, ""))
            return Status("failed", f"后台进程退出了（代码 {code}）" + (f"：{tail}" if tail else ""))
        if READY_MARK in output:
            return Status("running", f"每 {self.minutes} 分钟提醒一次")
        return Status("starting", "正在启动……")

    def _read_log(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


def _last_lines(text: str, n: int = 3) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " / ".join(lines[-n:])[:300]
