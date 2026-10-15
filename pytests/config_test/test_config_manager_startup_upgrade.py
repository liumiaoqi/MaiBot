from typing import Any

from src.config import config as config_module
from src.config.config import Config, ConfigManager, ModelConfig
from src.config.default_model_config import create_default_model_config


def test_initialize_upgrades_bot_and_model_config_without_exit(monkeypatch):
    """启动路径：两份配置各读一次、都被自动升级、不退出（并转达"升级"这条日志）。

    ⚠️ 桩返回**真实 ModelConfig**（4 段追加）：`initialize` 现在会跑启动期环境引用预校验
    （`preflight_provider_env_references`），它要读 `api_providers` ⇒ 桩再返回 `object()`
    就不成立了。用真 ModelConfig 也比"随便一个对象"更贴近生产形态。
    """
    manager = ConfigManager()
    loaded_config_classes: list[type[Any]] = []
    warnings: list[Any] = []
    fake_model_config = create_default_model_config(ModelConfig)

    def fake_load_config_from_file(config_class, config_path, new_ver, override_repr=False):
        loaded_config_classes.append(config_class)
        if config_class is ModelConfig:
            return fake_model_config, True
        return Config.model_construct(), True

    monkeypatch.setattr(config_module, "load_config_from_file", fake_load_config_from_file)
    monkeypatch.setattr(ConfigManager, "_warn_if_vlm_not_configured", lambda self, model_config: warnings.append(model_config))

    manager.initialize()

    assert loaded_config_classes == [Config, ModelConfig]
    assert warnings == [manager.model_config]
