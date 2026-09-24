"""配置：读写 %APPDATA%\\jo-app\\config.json，所有默认值都在这里。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def data_dir() -> Path:
    """数据目录。Windows 下用 %APPDATA%\\jo-app，其他平台用 ~/.jo-app。"""
    base = os.environ.get("JOAPP_HOME")
    if base:
        d = Path(base)
    elif os.name == "nt" and os.environ.get("APPDATA"):
        d = Path(os.environ["APPDATA"]) / "jo-app"
    else:
        d = Path.home() / ".jo-app"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = data_dir() / "config.json"
DB_PATH = data_dir() / "jo.db"
REMINDER_LOG = data_dir() / "reminder.log"


@dataclass
class Config:
    # 定时提醒：开应用就在后台跑，退出应用一起关
    remind_enabled: bool = True
    remind_minutes: int = 60
    remind_voice: str = "喝水时间到了，顺便起来活动一下吧"  # 空串 = 不念
    remind_popup: str = "休息下吧"  # 空串 = 不弹窗

    # 界面：折叠起来的分组（"daily" / "today" / "weekly" / "yearly"）。
    # 「每天」不管存的是什么，每次启动都会展开。
    collapsed: list = field(default_factory=list)

    _extra: dict = field(default_factory=dict)


def load() -> Config:
    if not CONFIG_PATH.exists():
        cfg = Config()
        save(cfg)
        return cfg
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Config()
    known = {f for f in Config.__dataclass_fields__ if not f.startswith("_")}
    cfg = Config(**{k: v for k, v in raw.items() if k in known})
    # 旧版本的键（llm_enabled、focus_minutes……）原样留着，不删用户的文件内容
    cfg._extra = {k: v for k, v in raw.items() if k not in known}
    return cfg


def save(cfg: Config) -> None:
    data = {k: v for k, v in asdict(cfg).items() if not k.startswith("_")}
    data.update(cfg._extra)
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
