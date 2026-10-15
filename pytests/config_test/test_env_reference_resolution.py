"""3 段 · 密钥引用化：``${VAR}`` 解析（F4）的回归测试。

覆盖判据门①（命中 / 未命中报错 / 非引用明文原样）与冻结契约 F4 的两条边界：

- **只解析被引用的字段位**（``api_providers[].api_key``）；``auth_query_name`` /
  ``default_headers`` / ``default_query`` 里的 ``${VAR}`` 按契约**不解析**，保持字面量；
- **解析不写回文件**：正常读取后文件里仍是 ``${VAR}``，明文不进文件。

以及两处"接线完整性"：``docker-compose.yml`` 注入的键名与 ``.env.example`` 里的键名必须一致，
``.env.example`` 只放键名不放值（值只在宿主 ``.env`` 里）。

实现走的是**生产路径**（``load_config_from_file`` → ``ConfigBase.from_dict`` → pydantic →
``APIProvider.model_post_init``），不是"测试自己 init 自己"。
夹具一律用**假值**；配置文件写在 ``tmp_path``，活配置一个字节都不碰。
"""

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.config.config import MODEL_CONFIG_VERSION, ModelConfig, load_config_from_file
from src.config.model_configs import (
    APIProvider,
    ConfigEnvReferenceError,
    raw_api_key_of,
    resolve_env_references,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# 变量名带 3SEG 后缀：与仓库里别的测试/真值不串味
FAKE_ENV_VAR = "MAIBOT_TEST_3SEG_FAKE_API_KEY"
FAKE_KEY_VALUE = "sk-fake-3seg-not-a-real-key"
FAKE_LITERAL_KEY = "sk-fake-3seg-literal-not-a-real-key"
REFERENCE_TEXT = "${" + FAKE_ENV_VAR + "}"

_FIELD_PATH = "api_providers[FakeProvider].api_key"

# `- NAME=${NAME...}`：环境注入的形态（值为空时用 `:-`，双读期不能因此拒绝起容器）
_INJECTION_PATTERN = re.compile(r"^\s*-\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\$\{\s*\1[^}]*\}\s*$", re.MULTILINE)


def _write_model_config(path: Path, api_key_value: str) -> None:
    """写一份最小可用的 model_config.toml（版本=当前版本，不触发自动升级改写）。"""
    path.write_text(
        f"""[inner]
version = "{MODEL_CONFIG_VERSION}"

[[models]]
model_identifier = "fake-model-3seg"
name = "fake-model-3seg"
api_provider = "FakeProvider"

[[api_providers]]
name = "FakeProvider"
base_url = "https://fake.invalid/v1"
api_key = "{api_key_value}"
auth_type = "bearer"
auth_query_name = "{REFERENCE_TEXT}"

[api_providers.default_headers]
X-Trace = "{REFERENCE_TEXT}"

[api_providers.default_query]
q = "{REFERENCE_TEXT}"
""",
        encoding="utf-8",
    )


def _env_example_entries() -> list[tuple[str, str]]:
    """读仓根 `.env.example` 的 (键名, 值) 列表——注释与空行跳过。"""
    entries: list[tuple[str, str]] = []
    for raw_line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        entries.append((name.strip(), value.strip()))
    return entries


class TestReferenceResolution:
    """判据门①：三种情形（走生产加载路径）。"""

    def test_reference_hit_resolves_and_stays_reference_on_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(FAKE_ENV_VAR, FAKE_KEY_VALUE)
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, REFERENCE_TEXT)

        config, updated = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

        provider = config.api_providers[0]
        assert provider.api_key == FAKE_KEY_VALUE

        # 边界：只有 api_key 是解析位，其余字段按契约保持字面量
        assert provider.auth_query_name == REFERENCE_TEXT
        assert provider.default_headers["X-Trace"] == REFERENCE_TEXT
        assert provider.default_query["q"] == REFERENCE_TEXT

        # 解析不写回文件：明文不进文件，引用还在
        on_disk = config_path.read_text(encoding="utf-8")
        assert REFERENCE_TEXT in on_disk
        assert FAKE_KEY_VALUE not in on_disk
        assert updated is False

    def test_reference_missing_reports_variable_and_field_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, REFERENCE_TEXT)

        # pydantic 会把 model_post_init 里的 ValueError 包成 ValidationError，
        # 两种形态都算合格——判据是**文本**里找得到变量名与字段路径
        with pytest.raises((ConfigEnvReferenceError, ValidationError)) as excinfo:
            load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

        message = str(excinfo.value)
        assert FAKE_ENV_VAR in message
        assert _FIELD_PATH in message

    def test_plaintext_api_key_is_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """双读期：老配置（明文）照常工作，不允许"只有引用能跑"。"""
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, FAKE_LITERAL_KEY)

        config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

        assert config.api_providers[0].api_key == FAKE_LITERAL_KEY


class TestResolutionBoundary:
    """解析函数本身的形状：单趟替换、空值算缺、不认领的 `${...}` 保持字面量。"""

    def test_blank_variable_counts_as_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(FAKE_ENV_VAR, "   ")

        with pytest.raises(ConfigEnvReferenceError) as excinfo:
            resolve_env_references(REFERENCE_TEXT, field_path=_FIELD_PATH)

        assert excinfo.value.variable == FAKE_ENV_VAR
        assert excinfo.value.field_path == _FIELD_PATH

    def test_resolution_is_single_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """替换结果里再出现 `${...}` 不二次展开——否则环境变量能间接读到别的变量。"""
        monkeypatch.setenv(FAKE_ENV_VAR, "prefix-${MAIBOT_TEST_3SEG_UNSET}-suffix")

        assert (
            resolve_env_references(REFERENCE_TEXT, field_path=_FIELD_PATH)
            == "prefix-${MAIBOT_TEST_3SEG_UNSET}-suffix"
        )


class TestRawApiKeyAccessor:
    """写回路径的取用点：`raw_api_key_of` 给的是**盘上原文**，不是解析后的明文。

    背景（3 段实测的写回洞）：解析就地改写 `api_key`，而 `write_config_to_file` 逐字段
    ``getattr`` 取模板 ⇒ 不区分就会把真密钥写回文件。
    """

    def test_reference_keeps_raw_text_for_writeback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(FAKE_ENV_VAR, FAKE_KEY_VALUE)
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, REFERENCE_TEXT)

        config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)
        provider = config.api_providers[0]

        assert provider.api_key == FAKE_KEY_VALUE
        assert raw_api_key_of(provider) == REFERENCE_TEXT

    def test_plaintext_raw_equals_value(self, tmp_path: Path) -> None:
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, FAKE_LITERAL_KEY)

        config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)
        provider = config.api_providers[0]

        assert raw_api_key_of(provider) == FAKE_LITERAL_KEY

    def test_empty_key_is_captured_not_missing(self) -> None:
        """空 key（auth_type=none 合法）要能区分于"没留原文"——否则写回守卫会误拒。"""
        provider = APIProvider(name="NoAuth", base_url="https://fake.invalid/v1", api_key="", auth_type="none")

        assert raw_api_key_of(provider) == ""

    def test_unparsed_object_has_no_raw(self) -> None:
        """没走解析路径 ⇒ 拿不到原文（写回方应据此拒绝，不许猜）。

        ⚠️ 实测：`model_construct` **也会**触发 `model_post_init`（raw 照样留下），
        所以 `None` 只在"子类跳过 model_post_init"这类路径上出现——防御性分支，
        但仍要保证语义：**拿不到原文 ≠ 空字符串**。
        """

        class _SkippingProvider(APIProvider):
            """故意不调 `super().model_post_init()`：模拟"没经过解析路径"。"""

            def model_post_init(self, context: Any = None) -> None:
                pass

        provider = _SkippingProvider(name="Skipped", base_url="https://fake.invalid/v1", api_key="sk-x")

        assert provider.api_key == "sk-x"
        assert raw_api_key_of(provider) is None


class TestEnvInjectionWiring:
    """接线完整性：compose 注入的键名 ⇔ `.env.example` 的键名（不许各写各的）。"""

    def test_compose_injects_exactly_the_example_keys(self) -> None:
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        injected = set(_INJECTION_PATTERN.findall(compose_text))
        example_keys = {name for name, _ in _env_example_entries()}

        assert injected, "docker-compose.yml 里没有找到 `- NAME=${NAME}` 形态的环境注入"
        assert injected == example_keys, (
            f"compose 注入 {sorted(injected)} 与 .env.example 的键 {sorted(example_keys)} 不一致"
        )

    def test_env_example_carries_keys_without_values(self) -> None:
        entries = _env_example_entries()

        assert entries, ".env.example 里没有键名"
        assert all(value == "" for _, value in entries), "`.env.example` 只放键名，值只能进宿主 `.env`"
