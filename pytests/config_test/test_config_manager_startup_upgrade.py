from typing import Any

from src.config import config as config_module
from src.config.config import Config, ConfigManager, ModelConfig


def test_initialize_upgrades_bot_and_model_config_without_exit(monkeypatch):
    manager = ConfigManager()
    loaded_config_classes: list[type[Any]] = []
    warnings: list[Any] = []

    def fake_load_config_from_file(config_class, config_path, new_ver, override_repr=False):
        loaded_config_classes.append(config_class)
        return object(), True

    monkeypatch.setattr(config_module, "load_config_from_file", fake_load_config_from_file)
    monkeypatch.setattr(ConfigManager, "_warn_if_vlm_not_configured", lambda self, model_config: warnings.append(model_config))

    manager.initialize()

    assert loaded_config_classes == [Config, ModelConfig]
    assert warnings == [manager.model_config]
