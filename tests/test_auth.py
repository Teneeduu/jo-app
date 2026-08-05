"""凭据探测的测试。

重点是那几个反直觉的分支：空环境变量会占位、环境变量会盖住 profile、
指定了不存在的 profile 是错误而不是回退。
"""

import json

import pytest

from joapp.agent import auth
from joapp.agent.auth import Source

ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_PROFILE",
    "ANTHROPIC_CONFIG_DIR",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """一个干净的环境 + 一个空的 profile 目录。"""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    return tmp_path


def write_profile(root, name: str = "default") -> None:
    creds = root / "credentials"
    creds.mkdir(parents=True, exist_ok=True)
    (creds / f"{name}.json").write_text(json.dumps({"access_token": "x"}))


def test_nothing_configured(clean_env):
    creds = auth.detect()
    assert creds.source is Source.NONE
    assert not creds.available


def test_api_key_wins(clean_env, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    creds = auth.detect()
    assert creds.source is Source.API_KEY
    assert creds.available


def test_auth_token_is_recognised(clean_env, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "oat-test")
    assert auth.detect().source is Source.AUTH_TOKEN


def test_login_profile_alone_is_enough(clean_env):
    """这是修复的重点 —— 没有任何环境变量，光靠登录也该算有凭据。"""
    write_profile(clean_env)
    creds = auth.detect()
    assert creds.source is Source.PROFILE
    assert creds.available
    assert creds.profile == "default"


def test_env_key_shadows_a_logged_in_profile(clean_env, monkeypatch):
    write_profile(clean_env)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    creds = auth.detect()
    assert creds.source is Source.API_KEY
    assert creds.warning and "盖住" in creds.warning


def test_empty_key_is_not_treated_as_absent(clean_env, monkeypatch):
    """空字符串照样占住优先级，然后拿着空 key 去请求 —— 不能当成「没设置」。"""
    write_profile(clean_env)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    creds = auth.detect()
    assert creds.source is Source.NONE
    assert creds.warning is not None


def test_named_profile_is_selected(clean_env, monkeypatch):
    write_profile(clean_env, "default")
    write_profile(clean_env, "work")
    monkeypatch.setenv("ANTHROPIC_PROFILE", "work")
    creds = auth.detect()
    assert creds.source is Source.PROFILE
    assert creds.profile == "work"


def test_missing_named_profile_does_not_fall_back(clean_env, monkeypatch):
    """指定了不存在的 profile 是错误，不会静默用默认的。"""
    write_profile(clean_env, "default")
    monkeypatch.setenv("ANTHROPIC_PROFILE", "nope")
    creds = auth.detect()
    assert creds.source is Source.NONE
    assert "nope" in creds.detail


def test_default_is_preferred_among_several(clean_env):
    write_profile(clean_env, "work")
    write_profile(clean_env, "default")
    assert auth.detect().profile == "default"


def test_profiles_lists_what_is_on_disk(clean_env):
    assert auth.profiles() == []
    write_profile(clean_env, "b")
    write_profile(clean_env, "a")
    assert auth.profiles() == ["a", "b"]


def test_config_dir_honours_the_override(clean_env, tmp_path):
    assert auth.config_dir() == tmp_path
