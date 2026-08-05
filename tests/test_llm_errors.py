"""异常分类的测试。

这一层的价值全在「说对话」—— 没额度和没登录对用户来说是完全不同的两件事，
混成一句「离线模式」会让人查错方向（真发生过）。
"""

import pytest

from joapp.agent.llm import HINTS, LLMUnavailable, Reason, classify


class FakeAPIError(Exception):
    """模拟 SDK 的异常：带 status_code，消息里是服务端原文。"""

    def __init__(self, status_code=None, message=""):
        self.status_code = status_code
        super().__init__(message)


def test_low_credit_is_billing_not_auth():
    """真实踩到的那个：登录是好的，只是账户没额度。"""
    exc = FakeAPIError(
        400,
        "Error code: 400 - {'type': 'error', 'error': {'type': "
        "'invalid_request_error', 'message': 'Your credit balance is too low "
        "to access the Anthropic API. Please go to Plans & Billing...'}}",
    )
    assert classify(exc) is Reason.BILLING


def test_billing_hint_mentions_the_subscription_trap():
    """Pro/Max 订阅不含 API 用量 —— 不说清楚的话用户会一直以为自己付过钱了。"""
    hint = HINTS[Reason.BILLING]
    assert "Pro" in hint and "API" in hint


def test_unauthorized_is_auth():
    assert classify(FakeAPIError(401, "authentication_error")) is Reason.AUTH


def test_forbidden_is_auth():
    assert classify(FakeAPIError(403, "permission denied")) is Reason.AUTH


def test_rate_limit():
    assert classify(FakeAPIError(429, "rate_limit_error")) is Reason.RATE_LIMIT


def test_server_errors():
    assert classify(FakeAPIError(500, "api_error")) is Reason.SERVER
    assert classify(FakeAPIError(529, "overloaded_error")) is Reason.SERVER


def test_connection_problems_are_network():
    class APIConnectionError(Exception):
        pass

    assert classify(APIConnectionError("connection refused")) is Reason.NETWORK

    class APITimeoutError(Exception):
        pass

    assert classify(APITimeoutError("timed out")) is Reason.NETWORK


def test_unknown_falls_back_to_other():
    assert classify(ValueError("???")) is Reason.OTHER


def test_billing_beats_a_bare_400():
    """没额度也是 400 —— 不能被当成普通的坏请求。"""
    assert classify(FakeAPIError(400, "bad request")) is Reason.OTHER
    assert classify(FakeAPIError(400, "credit balance too low")) is Reason.BILLING


def test_every_reason_has_a_hint():
    for reason in Reason:
        assert HINTS.get(reason), f"{reason} 没有对应的提示文案"


def test_exception_carries_reason_and_hint():
    exc = LLMUnavailable(Reason.BILLING, "400 ...")
    assert exc.reason is Reason.BILLING
    assert "额度" in exc.hint
    assert exc.detail == "400 ..."


# --- planner 的状态判断 ---


@pytest.fixture
def planner(tmp_path, monkeypatch):
    from joapp.agent import auth
    from joapp.agent.planner import Planner
    from joapp.config import Config
    from joapp.core.store import Store

    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(
        auth, "detect", lambda: auth.Credentials(auth.Source.PROFILE, "已登录", "default")
    )
    return Planner(Config(), Store(tmp_path / "t.db"))


def test_failing_distinguishes_from_disconnected(planner):
    assert planner.use_llm is True
    assert planner.failing is False
    assert planner.llm_working is True

    planner.last_error = LLMUnavailable(Reason.BILLING, "no credits")
    assert planner.use_llm is True  # 凭据没问题
    assert planner.failing is True  # 但调不通
    assert planner.llm_working is False  # 所以界面该给格式提示


def test_status_line_explains_a_failure(planner):
    planner.last_error = LLMUnavailable(Reason.BILLING, "no credits")
    line = planner.status_line
    assert "已登录" in line and "调用失败" in line and "额度" in line


def test_status_line_when_connected_and_fine(planner):
    assert planner.status_line == "Claude：已登录"
