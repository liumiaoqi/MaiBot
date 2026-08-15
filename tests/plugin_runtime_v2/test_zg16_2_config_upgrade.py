"""ZG16-2 配置升级钩子单元测试。

覆盖 _add_token_budget_config 迁移函数：旧配置补默认值、
已有字段不覆盖、返回迁移原因列表、ConfigUpgradeHook 注册、
bot_config.toml 模板含新配置项。
"""


from pathlib import Path

from src.config.config_upgrade_hooks import (
    BOT_CONFIG_UPGRADE_HOOKS,
    ConfigUpgradeHook,
    _add_token_budget_config,
)


# ════════════════════════════════════════════════════════════════════
# 旧配置无 token 预算字段
# ════════════════════════════════════════════════════════════════════


def test_old_config_without_token_budget_fields():
    """旧配置无 token 预算字段 → 自动补默认值（false/0.8/0.16）不崩溃。"""
    data: dict = {"chat": {"max_context_size": 40}}
    reasons = _add_token_budget_config(data)
    assert data["chat"]["enable_token_budget"] is False
    assert data["chat"]["token_threshold_ratio"] == 0.8
    assert data["chat"]["token_retain_ratio"] == 0.16
    assert len(reasons) > 0


def test_old_config_without_chat_section():
    """旧配置无 chat 段 → 自动创建 chat 子段并补默认值。"""
    data: dict = {}
    reasons = _add_token_budget_config(data)
    assert data["chat"]["enable_token_budget"] is False
    assert data["chat"]["token_threshold_ratio"] == 0.8
    assert data["chat"]["token_retain_ratio"] == 0.16
    assert len(reasons) > 0


# ════════════════════════════════════════════════════════════════════
# 已有字段不覆盖
# ════════════════════════════════════════════════════════════════════


def test_existing_fields_not_overwritten():
    """enable_token_budget=true 已存在 → 不覆盖。"""
    data: dict = {
        "chat": {
            "enable_token_budget": True,
            "token_threshold_ratio": 0.9,
            "token_retain_ratio": 0.2,
        }
    }
    _add_token_budget_config(data)
    assert data["chat"]["enable_token_budget"] is True
    assert data["chat"]["token_threshold_ratio"] == 0.9
    assert data["chat"]["token_retain_ratio"] == 0.2


def test_partial_existing_fields_not_overwritten():
    """仅 enable_token_budget 已存在 → 只补其余两个。"""
    data: dict = {"chat": {"enable_token_budget": True}}
    _add_token_budget_config(data)
    assert data["chat"]["enable_token_budget"] is True  # 不覆盖
    assert data["chat"]["token_threshold_ratio"] == 0.8  # 补默认
    assert data["chat"]["token_retain_ratio"] == 0.16  # 补默认


# ════════════════════════════════════════════════════════════════════
# 返回迁移原因列表
# ════════════════════════════════════════════════════════════════════


def test_returns_reason_list():
    """返回迁移原因列表（list[str]）。"""
    data: dict = {"chat": {"max_context_size": 40}}
    reasons = _add_token_budget_config(data)
    assert isinstance(reasons, list)
    assert len(reasons) > 0
    for reason in reasons:
        assert isinstance(reason, str)


def test_returns_empty_list_when_no_change():
    """已有全部字段 → 返回空列表（无变更）。"""
    data: dict = {
        "chat": {
            "enable_token_budget": True,
            "token_threshold_ratio": 0.9,
            "token_retain_ratio": 0.2,
        }
    }
    reasons = _add_token_budget_config(data)
    assert reasons == []


# ════════════════════════════════════════════════════════════════════
# ConfigUpgradeHook 注册
# ════════════════════════════════════════════════════════════════════


def test_hook_registered_in_bot_config_upgrade_hooks():
    """ConfigUpgradeHook 注册到 BOT_CONFIG_UPGRADE_HOOKS（target_version="8.28.1"）。"""
    hook = next(h for h in BOT_CONFIG_UPGRADE_HOOKS if h.target_version == "8.28.1")
    assert isinstance(hook, ConfigUpgradeHook)
    assert "bot_config.toml" in hook.config_names
    assert hook.migrate is _add_token_budget_config


def test_hook_target_version_is_8_28_1():
    """8.28.1 钩子唯一存在。"""
    matching = [h for h in BOT_CONFIG_UPGRADE_HOOKS if h.target_version == "8.28.1"]
    assert len(matching) == 1


# ════════════════════════════════════════════════════════════════════
# bot_config.toml 模板含新配置项
# ════════════════════════════════════════════════════════════════════


def test_bot_config_template_contains_token_budget_fields():
    """bot_config.toml 模板含 enable_token_budget/token_threshold_ratio/token_retain_ratio。"""
    toml_path = Path(__file__).resolve().parents[2] / "config" / "bot_config.toml"
    content = toml_path.read_text(encoding="utf-8")
    assert "enable_token_budget" in content
    assert "token_threshold_ratio" in content
    assert "token_retain_ratio" in content


def test_bot_config_template_has_correct_defaults():
    """bot_config.toml 模板默认值与迁移函数一致。"""
    toml_path = Path(__file__).resolve().parents[2] / "config" / "bot_config.toml"
    content = toml_path.read_text(encoding="utf-8")
    assert "enable_token_budget = false" in content
    assert "token_threshold_ratio = 0.8" in content
    assert "token_retain_ratio = 0.16" in content