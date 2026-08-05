"""搞清楚「现在到底有没有凭据、是哪一种」。

关键认知：**环境变量里没有 ANTHROPIC_API_KEY，不代表没有凭据。**
SDK 自己会按顺序找，跑过 `ant auth login` 之后裸的 Anthropic() 客户端就能用。
所以这里只做展示和引导，真正的解析交给 SDK —— 我们不去替它挑凭据，
免得两边的优先级对不上。

SDK 的查找顺序（先命中先用）：
    1. ANTHROPIC_API_KEY
    2. ANTHROPIC_AUTH_TOKEN
    3. ANTHROPIC_PROFILE 指定的 / 当前激活的 OAuth profile
    4. Workload Identity Federation 的那组环境变量（给 CI 用，桌面端不管）
    5. 磁盘上的默认 profile
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

DOWNLOAD_URL = "https://github.com/anthropics/anthropic-cli/releases"
CONSOLE_URL = "https://platform.claude.com/settings/keys"


class Source(str, Enum):
    API_KEY = "api_key"  # ANTHROPIC_API_KEY
    AUTH_TOKEN = "auth_token"  # ANTHROPIC_AUTH_TOKEN
    PROFILE = "profile"  # ant auth login 留下的 OAuth profile
    NONE = "none"


@dataclass
class Credentials:
    source: Source
    detail: str  # 一句人话，UI 直接显示
    profile: str | None = None
    warning: str | None = None  # 有坑的时候提示用户

    @property
    def available(self) -> bool:
        return self.source is not Source.NONE


def config_dir() -> Path:
    """Anthropic CLI / SDK 存 profile 的地方。"""
    override = os.environ.get("ANTHROPIC_CONFIG_DIR")
    if override:
        return Path(override)
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "Anthropic"
    return Path.home() / ".config" / "anthropic"


def profiles() -> list[str]:
    """磁盘上已经登录过的 profile 名字。"""
    creds = config_dir() / "credentials"
    if not creds.is_dir():
        return []
    return sorted(p.stem for p in creds.glob("*.json"))


def detect() -> Credentials:
    """按 SDK 的优先级判断当前会用哪一种凭据。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    saved = profiles()
    wanted = os.environ.get("ANTHROPIC_PROFILE")

    # 空字符串也会占住优先级，然后拿着空 key 去请求 —— 这个坑值得单独喊一声
    if key is not None and not key.strip():
        return Credentials(
            Source.NONE,
            "ANTHROPIC_API_KEY 是空的",
            warning="空的环境变量照样会盖住 profile。彻底删掉它（不是设成空）再试。",
        )
    if key:
        warning = None
        if saved:
            warning = (
                f"环境变量会盖住已登录的 profile（{', '.join(saved)}）。"
                "想用登录凭据就把 ANTHROPIC_API_KEY 删掉。"
            )
        return Credentials(Source.API_KEY, "用的是 ANTHROPIC_API_KEY", warning=warning)

    if token:
        return Credentials(Source.AUTH_TOKEN, "用的是 ANTHROPIC_AUTH_TOKEN")

    if wanted:
        # 指定了不存在的 profile 是错误，不会静默回退到默认
        if wanted in saved:
            return Credentials(Source.PROFILE, f"已登录（profile: {wanted}）", wanted)
        return Credentials(
            Source.NONE,
            f"ANTHROPIC_PROFILE 指到了不存在的 profile：{wanted}",
            warning="指定了不存在的 profile 是错误，不会回退到默认。",
        )

    if saved:
        name = "default" if "default" in saved else saved[0]
        return Credentials(Source.PROFILE, f"已登录（profile: {name}）", name)

    return Credentials(Source.NONE, "还没连 Claude")


# --- 引导用户去登录 ---------------------------------------------------------

WINGET_ID = "Anthropic.Ant"  # Claude Platform CLI


def cli_path() -> str | None:
    """找 ant CLI。

    不能只看 PATH —— 进程启动时就把 PATH 快照下来了，用户在应用跑着的时候
    装完 ant，`which` 照样找不到。所以补一条 winget 的 shim 目录。
    """
    found = shutil.which("ant")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for candidate in (
            Path(local) / "Microsoft" / "WinGet" / "Links" / "ant.exe",
            Path(local) / "Programs" / "ant" / "ant.exe",
        ):
            if candidate.is_file():
                return str(candidate)
    return None


def launch_install_and_login() -> bool:
    """开个可见的控制台，装 ant 然后立刻走登录。

    装包要好几分钟且会刷进度，藏在后台反而让人以为卡死了，所以故意开窗口。
    """
    if os.name != "nt":
        return False
    script = (
        f"winget install --id {WINGET_ID} -e --source winget --scope user "
        "--accept-package-agreements --accept-source-agreements; "
        "if ($LASTEXITCODE -eq 0) { "
        "  $ant = (Get-Command ant -ErrorAction SilentlyContinue).Source; "
        "  if (-not $ant) { $ant = Join-Path $env:LOCALAPPDATA "
        "'Microsoft\\WinGet\\Links\\ant.exe' } ; "
        "  & $ant auth login "
        "} else { Write-Host '安装失败，可以去 GitHub releases 手动下载。' }; "
        "Write-Host ''; Read-Host '完成后按回车关闭'"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return True
    except OSError:
        return False


def save_api_key(value: str) -> None:
    """把 key 写进用户环境变量，并让当前进程立刻生效。

    直接写注册表而不是 `setx` —— setx 会把 key 摆在命令行上，任务管理器里能看见。
    """
    value = value.strip()
    os.environ["ANTHROPIC_API_KEY"] = value  # 当前进程立刻可用，不用重启

    if os.name != "nt":
        return
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "ANTHROPIC_API_KEY", 0, winreg.REG_SZ, value)

    # 通知其他进程环境变量变了（不广播的话新开的终端要重登录才看得到）
    import ctypes

    ctypes.windll.user32.SendMessageTimeoutW(
        0xFFFF, 0x001A, 0, "Environment", 0x0002, 1000, None
    )


def looks_like_api_key(value: str) -> bool:
    value = value.strip()
    return value.startswith("sk-ant-") and len(value) > 20


def launch_login(profile: str | None = None) -> bool:
    """开一个新控制台跑 `ant auth login`，浏览器会自己弹出来。

    成功启动返回 True。登录是否真的完成要之后重新 detect() 才知道。
    """
    ant = cli_path()
    if not ant:
        return False
    cmd = [ant, "auth", "login"]
    if profile:
        cmd += ["--profile", profile]
    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    try:
        subprocess.Popen(cmd, creationflags=flags)
        return True
    except OSError:
        return False
