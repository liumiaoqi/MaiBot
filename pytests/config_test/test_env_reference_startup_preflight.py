"""4 段追加（lead 裁定②）· **启动期环境引用预校验**的回归测试。

## 为什么要有这一层

解析迁到注入边界之后，"缺变量"从**启动失败**退化成"**首次建客户端才炸**"
——容器 `ready=True`、心跳正常，直到用户第一条消息进来才失败。这是**失败响度上的退步**，
而本仓规矩是"未接线不得静默跳过：要么接线，要么初始化失败出声"（`AGENTS §七` #4），
dsh 口径是"**配置错误要响亮**"。⇒ `ConfigManager.initialize` 里补一次**只读**的预校验。

## 与其它两条判据的分工（三条一起才说得清"谁拦的"）

| 判据 | 位置 | 断言 |
|---|---|---|
| **加载器不拦** | `test_env_reference_resolution.py::test_loader_alone_does_not_check_the_variable` | `load_config_from_file` 缺变量也**照常返回** |
| **启动期拦**（本文件） | `ConfigManager.initialize` | 缺变量 ⇒ **类型化错误**、带变量名与字段路径 |
| **注入边界给真值** | `test_env_reference_injection_boundary.py` | 工厂拿到解析值、配置对象仍是引用 |

## 四条判据（lead 给的）

1. 缺变量 ⇒ 启动期类型化错误（带变量名与字段路径）；
2. 变量齐备 ⇒ 正常启动；
3. **不写回**：盘上仍是 ``${VAR}``（启动期校验是**只读**的）；
4. 环境里没有该变量的**明文配置**不受影响（双读期）。

⚠️ 夹具一律假值；两份配置都落在 ``tmp_path``（`CONFIG_DIR` 用 monkeypatch 改指过去），
**活配置一个字节都不碰**。
"""

import logging  # noqa: TID251 — 仅取 `logging.CRITICAL` 这个整数常量配合 pytest 的 caplog；
# 用 `src.common.logger.get_logger()` 取不到它（那是项目自己的 logger 封装），而过滤器层级
# 必须与生产代码一致，否则本用例会因为"记录被过滤掉"而假绿。
from pathlib import Path

import pytest
import tomlkit

from src.config import config as config_module
from src.config.config import (
    CONFIG_VERSION,
    MODEL_CONFIG_VERSION,
    ConfigManager,
    ModelConfig,
    generate_new_config_file,
)
from src.config.model_configs import ConfigEnvReferenceError

# 变量名/值带 4SEG 前缀，与仓库别的测试不串味
FAKE_ENV_VAR = "MAIBOT_TEST_4SEG_PREFLIGHT_KEY"
FAKE_KEY_VALUE = "sk-fake-4seg-preflight-not-a-real-key"
FAKE_LITERAL_KEY = "sk-fake-4seg-preflight-literal"
REFERENCE_TEXT = "${" + FAKE_ENV_VAR + "}"

STARTUP_LOGGER = "config.model_configs"


def _prepare_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, api_key_value: str) -> Path:
    """在 ``tmp_path`` 造一对**可启动**的配置，并把模块级 ``CONFIG_DIR`` 指过去。

    做法（**不是**手搓最小 TOML）：先用生产入口 `generate_new_config_file` 生成两份完整配置
    （bot 用 ``Config`` 默认、model 用 ``create_default_model_config``），再**只改 api_key 那一行**。
    ⇒ 夹具与真配置同形，`initialize()` 里别的校验不会因为"夹具缺字段"而先炸，
    判据能精准打到预校验上。
    """
    bot_path = tmp_path / "bot_config.toml"
    model_path = tmp_path / "model_config.toml"
    generate_new_config_file(config_module.Config, bot_path, CONFIG_VERSION)
    generate_new_config_file(ModelConfig, model_path, MODEL_CONFIG_VERSION, override_repr=True)

    document = tomlkit.parse(model_path.read_text(encoding="utf-8"))
    document["api_providers"][0]["api_key"] = api_key_value
    model_path.write_text(tomlkit.dumps(document), encoding="utf-8")

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "BOT_CONFIG_PATH", bot_path)
    monkeypatch.setattr(config_module, "MODEL_CONFIG_PATH", model_path)
    return model_path


def _disk_api_key(model_path: Path) -> str:
    """取盘上第一个 provider 的 api_key（裸值，便于逐字断言）。"""
    document = tomlkit.parse(model_path.read_text(encoding="utf-8"))
    return str(document["api_providers"][0]["api_key"])


class TestStartupPreflight:
    """判据①②③④：启动期拦缺变量、放行齐备与明文、且**不写回**。"""

    def test_missing_variable_refuses_startup_with_name_and_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """判据①：缺变量 ⇒ 启动期**类型化**错误，消息带变量名与字段路径，盘上字节不变。

        ⚠️ 这条与"加载器不拦"成对：`load_config_from_file` 对同一份文件**不会**报错
        （见 `test_env_reference_resolution.py`）⇒ 报错的一定是启动期预校验。
        """
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        model_path = _prepare_config_dir(tmp_path, monkeypatch, REFERENCE_TEXT)
        before = model_path.read_bytes()

        with pytest.raises(ConfigEnvReferenceError) as excinfo:
            ConfigManager().initialize()

        assert excinfo.value.variable == FAKE_ENV_VAR
        assert excinfo.value.field_path.endswith(".api_key")
        assert FAKE_ENV_VAR in str(excinfo.value)
        # 判据③（失败那一支也要查）：拒绝启动**不改文件**
        assert model_path.read_bytes() == before, "启动期预校验动了文件"
        assert _disk_api_key(model_path) == REFERENCE_TEXT

    def test_missing_variable_is_reported_on_both_channels(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """异常双通道：拒绝启动要**既进日志、又上报 port**（债务原则：不得单通道）。

        只测"抛了异常"是不够的——`except` 里只 report 不 logger（或反之）是高频缺陷模式，
        而这条路径正是"容器起不来时唯一能看到的现场"。
        """
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        _prepare_config_dir(tmp_path, monkeypatch, REFERENCE_TEXT)
        reported: list[tuple] = []

        class _ProbePort:
            """把 CRITICAL 上报记下来（port 未注册时这条路径整个跳过，故必须注入）。"""

            def report(self, level, message, exception=None, **kwargs):  # noqa: ANN001, ANN003 — 探针只对齐被调用的签名
                reported.append((level, message, type(exception).__name__ if exception else None))

        monkeypatch.setattr(
            "src.core.error_escalation_port_registry.get_error_escalation_port", lambda: _ProbePort()
        )

        with caplog.at_level(logging.CRITICAL, logger=STARTUP_LOGGER):
            with pytest.raises(ConfigEnvReferenceError):
                ConfigManager().initialize()

        assert reported, "只进了日志、没有上报 port（单通道）"
        assert reported[0][2] == "ConfigEnvReferenceError"
        assert any(FAKE_ENV_VAR in record.getMessage() for record in caplog.records), "只上报、没进日志"

    def test_present_variable_starts_originally_and_keeps_reference_on_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """判据②③（正常支）：变量齐备 ⇒ 正常启动，且**盘上仍是** ``${VAR}``。"""
        monkeypatch.setenv(FAKE_ENV_VAR, FAKE_KEY_VALUE)
        model_path = _prepare_config_dir(tmp_path, monkeypatch, REFERENCE_TEXT)

        manager = ConfigManager()
        manager.initialize()

        assert manager.model_config is not None
        assert manager.global_config is not None
        # 判据③：预校验是只读的——盘上仍是引用，明文不进文件
        assert _disk_api_key(model_path) == REFERENCE_TEXT
        assert FAKE_KEY_VALUE not in model_path.read_text(encoding="utf-8")
        # 对象里也仍是引用（解析只在注入边界那一份副本上）
        assert manager.model_config.api_providers[0].api_key == REFERENCE_TEXT

    def test_plaintext_config_startswithout_any_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """判据④：明文配置**不受影响**——环境里根本没有这个变量也要能起（双读期）。"""
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        model_path = _prepare_config_dir(tmp_path, monkeypatch, FAKE_LITERAL_KEY)

        manager = ConfigManager()
        manager.initialize()

        assert manager.model_config is not None
        assert manager.model_config.api_providers[0].api_key == FAKE_LITERAL_KEY
        assert _disk_api_key(model_path) == FAKE_LITERAL_KEY

    def test_default_config_has_no_reference_and_starts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**反例/对照**：默认配置（``api_key = "your-api-key"`` 这种明文占位）也照常启动。

        防"预校验把没引用的东西也拦下来"这种过修——`resolve_env_references` 对非引用形态
        原样返回，这条钉住它。
        """
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        model_path = _prepare_config_dir(tmp_path, monkeypatch, "your-api-key")

        ConfigManager().initialize()

        assert _disk_api_key(model_path) == "your-api-key"
