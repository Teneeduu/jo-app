"""Claude API 客户端。整个应用里唯一联网的地方。

任何一步出问题（没装 SDK、没 key、断网、超时）都抛 LLMUnavailable，
由 planner 接住并降级到规则引擎 —— 应用永远不会因为模型挂了而不能用。
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from ..config import Config
from . import prompts

log = logging.getLogger(__name__)

MAX_TOKENS = 8000
TIMEOUT_SECONDS = 30.0


class Reason(str, Enum):
    NO_SDK = "no_sdk"
    NO_CREDENTIALS = "no_credentials"
    AUTH = "auth"
    BILLING = "billing"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    SERVER = "server"
    REFUSED = "refused"
    BAD_RESPONSE = "bad_response"
    OTHER = "other"


# 给用户看的话。每条都要能直接指向下一步动作，不能只说「失败了」。
HINTS = {
    Reason.NO_SDK: "没装 anthropic SDK，跑一下 pip install anthropic。",
    Reason.NO_CREDENTIALS: "还没连上 Claude。",
    Reason.AUTH: "凭据无效或已过期，重新登录一次（ant auth login）。",
    Reason.BILLING: (
        "账户没有 API 额度 —— 注意 Claude Pro/Max 订阅不含 API 用量，"
        "要在 Console 的 Plans & Billing 里单独充值。"
    ),
    Reason.RATE_LIMIT: "触发限流了，等一会儿会自己恢复。",
    Reason.NETWORK: "连不上 Anthropic，检查一下网络或代理。",
    Reason.SERVER: "Anthropic 服务端出错了，通常过一会儿就好。",
    Reason.REFUSED: "模型拒绝了这次请求。",
    Reason.BAD_RESPONSE: "返回的内容没法解析。",
    Reason.OTHER: "调用失败了。",
}


class LLMUnavailable(RuntimeError):
    """模型这条路走不通，调用方应该降级。

    带上分类，好让界面说清楚是「没连」还是「连了但没额度」——
    这两件事对用户来说完全不同，混成一句「离线模式」会让人查错方向。
    """

    def __init__(self, reason: Reason, message: str = ""):
        self.reason = reason
        self.detail = message
        super().__init__(message or reason.value)

    @property
    def hint(self) -> str:
        return HINTS.get(self.reason, HINTS[Reason.OTHER])


def classify(exc: Exception) -> Reason:
    """把 SDK 的异常翻译成一个我们能给出建议的类别。

    按状态码 + 报文关键字判断，不 import anthropic 的异常类型 ——
    SDK 的异常层次会变，字符串和状态码稳定得多。
    """
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    name = type(exc).__name__.lower()

    if "credit balance" in text or "billing" in text or "quota" in text:
        return Reason.BILLING
    if status == 401 or "authentication" in name:
        return Reason.AUTH
    if status == 403 or "permissiondenied" in name:
        return Reason.AUTH
    if status == 429 or "ratelimit" in name:
        return Reason.RATE_LIMIT
    if status is not None and status >= 500:
        return Reason.SERVER
    if "connection" in name or "timeout" in name:
        return Reason.NETWORK
    return Reason.OTHER


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._client = None

    def _client_or_raise(self):
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - 取决于安装环境
            raise LLMUnavailable(Reason.NO_SDK, str(e)) from e
        # 不传 api_key —— 让 SDK 自己按顺序找：环境变量、ant auth login 留下的
        # profile、WIF。我们替它挑就会跟它的优先级打架。
        try:
            self._client = anthropic.Anthropic(
                timeout=TIMEOUT_SECONDS, max_retries=1
            )
        except Exception as e:  # 一个凭据都找不到时 SDK 会在构造期就抛
            raise LLMUnavailable(Reason.NO_CREDENTIALS, str(e)) from e
        return self._client

    def _ask(self, instruction: str, schema: dict) -> dict[str, Any]:
        """发一次带 JSON schema 约束的请求，返回解析好的 dict。"""
        client = self._client_or_raise()
        try:
            response = client.messages.create(
                model=self.cfg.model,
                max_tokens=MAX_TOKENS,
                system=prompts.SYSTEM,
                output_config={
                    "effort": self.cfg.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                messages=[{"role": "user", "content": instruction}],
            )
        except Exception as e:  # SDK 的异常层次很多，这里统一分类后降级
            raise LLMUnavailable(classify(e), str(e)) from e

        if response.stop_reason == "refusal":
            raise LLMUnavailable(Reason.REFUSED, "stop_reason=refusal")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise LLMUnavailable(Reason.BAD_RESPONSE, "响应里没有文本内容")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMUnavailable(Reason.BAD_RESPONSE, f"不是合法 JSON: {e}") from e

    # --- 对外的两件事 ---------------------------------------------------

    def plan_tasks(self, raw: str, goal_titles: list[str]) -> dict[str, Any]:
        """把一段口语描述拆成任务清单。"""
        goals = "\n".join(f"- {g}" for g in goal_titles) or "（暂无）"
        return self._ask(
            prompts.PLAN_INSTRUCTION.format(raw=raw.strip(), goals=goals),
            prompts.TASK_SCHEMA,
        )

    def rewrite_nudge(self, kind: str, title: str, body: str, context: str) -> dict:
        """把规则引擎生成的提醒改写得更像人话。"""
        return self._ask(
            prompts.NUDGE_INSTRUCTION.format(
                context=context, kind=kind, title=title, body=body
            ),
            prompts.NUDGE_SCHEMA,
        )
