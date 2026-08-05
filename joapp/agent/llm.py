"""Claude API 客户端。整个应用里唯一联网的地方。

任何一步出问题（没装 SDK、没 key、断网、超时）都抛 LLMUnavailable，
由 planner 接住并降级到规则引擎 —— 应用永远不会因为模型挂了而不能用。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..config import Config
from . import prompts

log = logging.getLogger(__name__)

MAX_TOKENS = 8000
TIMEOUT_SECONDS = 30.0


class LLMUnavailable(RuntimeError):
    """模型这条路走不通，调用方应该降级。"""


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._client = None

    def _client_or_raise(self):
        if self._client is not None:
            return self._client
        if not self.cfg.api_key:
            raise LLMUnavailable("没有设置 ANTHROPIC_API_KEY")
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - 取决于安装环境
            raise LLMUnavailable("没装 anthropic SDK") from e
        self._client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=1)
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
        except Exception as e:  # SDK 的异常层次很多，这里统一降级
            raise LLMUnavailable(f"请求失败: {e}") from e

        if response.stop_reason == "refusal":
            raise LLMUnavailable("模型拒绝了这次请求")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise LLMUnavailable("响应里没有文本内容")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMUnavailable(f"返回的不是合法 JSON: {e}") from e

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
