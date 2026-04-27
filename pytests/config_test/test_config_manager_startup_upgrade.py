from typing import Any

import pytest

from src.config import config as config_module
from src.config.config import Config, ConfigManager, ModelConfig


class _StartupUpgradeExit(Exception):
    pass


def test_initialize_upgrades_bot_and_model_config_before_exit(monkeypatch):
    manager = ConfigManager()
    loaded_config_classes: list[type[Any]] = []
    exit_codes: list[int | None] = []

    def fake_load_config_from_file(config_class, config_path, new_ver, override_repr=False):
        loaded_config_classes.append(config_class)
        return object(), True

    def fake_exit(code: int | None = None):
        exit_codes.append(code)
        raise _StartupUpgradeExit

    monkeypatch.setattr(config_module, "load_config_from_file", fake_load_config_from_file)
    monkeypatch.setattr(config_module.sys, "exit", fake_exit)

    with pytest.raises(_StartupUpgradeExit):
        manager.initialize()

    assert loaded_config_classes == [Config, ModelConfig]
    assert exit_codes == [0]
