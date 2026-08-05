"""配置：读写 ~/.jo-app/config.json，所有默认值都在这里。"""

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


@dataclass
class Config:
    # 番茄钟 / 久坐提醒（分钟）
    focus_minutes: int = 45
    break_minutes: int = 5
    idle_threshold_minutes: int = 5  # 无输入超过这么久算离开电脑，暂停计时

    # 每日节奏
    morning_prompt_hour: int = 0  # 0 = 开机即问；否则等到这个整点之后才弹
    evening_review_hour: int = 22  # 晚间复盘提醒时间，None 关闭

    # 智能层
    # 只表示「我愿不愿意用」。有没有凭据是另一回事，由 agent/auth.py 探测，
    # 真正的凭据解析交给 SDK —— 见 Planner.use_llm。
    llm_enabled: bool = True
    model: str = "claude-opus-5"
    effort: str = "medium"  # low | medium | high | xhigh | max

    # 界面
    theme: str = "dark"
    nudge_seconds: int = 12  # 提醒气泡停留时长

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
    cfg._extra = {k: v for k, v in raw.items() if k not in known}
    return cfg


def save(cfg: Config) -> None:
    data = {k: v for k, v in asdict(cfg).items() if not k.startswith("_")}
    data.update(cfg._extra)
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
