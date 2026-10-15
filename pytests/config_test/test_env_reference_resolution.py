"""3 段 · 密钥引用化：``${VAR}`` 解析（F4）的回归测试（**4 段按归位后的口径改写过**）。

覆盖判据门①（命中 / 未命中报错 / 非引用明文原样）与冻结契约 F4 的两条边界：

- **只解析被引用的字段位**（``api_providers[].api_key``）；``auth_query_name`` /
  ``default_headers`` / ``default_query`` 里的 ``${VAR}`` 按契约**不解析**，保持字面量；
- **解析不写回文件**：正常读取后文件里仍是 ``${VAR}``，明文不进文件。

以及两处"接线完整性"：``docker-compose.yml`` 注入的键名与 ``.env.example`` 里的键名必须一致，
``.env.example`` 只放键名不放值（值只在宿主 ``.env`` 里）。

实现走的是**生产路径**（``load_config_from_file`` → ``ConfigBase.from_dict`` → pydantic →
``APIProvider.model_post_init``），不是"测试自己 init 自己"。
夹具一律用**假值**；配置文件写在 ``tmp_path``，活配置一个字节都不碰。

⚠️ **4 段（解析时机归位）改写了本文件的判据**：解析不再发生在加载期，所以"加载后对象里是
明文"这条旧判据**反转**成"加载后对象里仍是引用"。注入边界的判据（解析确实发生在建客户端时、
缺变量在那一刻报错、明文路径不受影响）在
``pytests/config_test/test_env_reference_injection_boundary.py``；"版本升级后盘上仍是引用"
的端到端判据在同目录 ``test_secret_writeback_guard.py``。
"""

import re
from pathlib import Path
from typing import Any

import pytest

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


def _api_key_disk_line(path: Path) -> str:
    """取文件里 ``api_key`` 那一行的裸值（逐字对，不用"包含"这种弱判据）。"""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("api_key") and "=" in stripped:
            return stripped.split("=", 1)[1].split("#", 1)[0].strip().strip('"')
    raise AssertionError("配置里找不到 api_key 行")


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
    """判据门①：三种情形（走生产加载路径）。

    ⚠️ **4 段（解析时机归位）后的口径**：加载期**不再**把 ``${VAR}`` 解成明文——
    配置对象里存的就是盘上原文，解析发生在"注入客户端之前"
    （见 `test_env_reference_injection_boundary.py`）。本类因此改判两件事：
    ① 加载后对象里**仍是引用**（不是明文）② 文件里的引用**一个字节都没被动**。
    """

    def test_reference_stays_reference_in_memory_and_on_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(FAKE_ENV_VAR, FAKE_KEY_VALUE)
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, REFERENCE_TEXT)

        config, updated = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

        provider = config.api_providers[0]
        # 归位后的硬判据：对象里是引用，**不是**解析值。
        # （旧行为是 `== FAKE_KEY_VALUE`——那正是"升级回写会把明文写回"的根因）
        assert provider.api_key == REFERENCE_TEXT
        assert provider.api_key != FAKE_KEY_VALUE

        # 边界：只有 api_key 是解析位，其余字段按契约保持字面量
        assert provider.auth_query_name == REFERENCE_TEXT
        assert provider.default_headers["X-Trace"] == REFERENCE_TEXT
        assert provider.default_query["q"] == REFERENCE_TEXT

        # 解析不写回文件：明文不进文件，引用还在（逐字对，防"引用被别的形态替换"）
        on_disk = config_path.read_text(encoding="utf-8")
        assert REFERENCE_TEXT in on_disk
        assert FAKE_KEY_VALUE not in on_disk
        assert updated is False
        assert _api_key_disk_line(config_path) == REFERENCE_TEXT

    def test_plaintext_api_key_is_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """双读期：老配置（明文）照常工作，不允许"只有引用能跑"（F4 判据④）。"""
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, FAKE_LITERAL_KEY)

        config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

        assert config.api_providers[0].api_key == FAKE_LITERAL_KEY

    def test_loader_alone_does_not_check_the_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**成对判据（加载器一侧）**：缺变量**不**在加载期炸——加载只管读文件。

        归位之前是"解析在 ``model_post_init`` ⇒ 加载即 ``ValidationError``、
        **容器起不来**"；归位之后加载器不认识引用能否解析（那是启动期预校验与注入边界的事）。

        ⚠️ 这条**必须与"启动期拦"那条成对**（`test_env_reference_startup_preflight.py`）：
        单留本条会把"缺变量没人管、首次调用才炸"钉成正确行为（那是失败响度的退步）；
        单留那条又说不清"到底是谁拦的"。两条一起，责任才划得清：**加载器不拦，启动期拦**。
        """
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, REFERENCE_TEXT)

        config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

        assert config.api_providers[0].api_key == REFERENCE_TEXT


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

    背景（3 段实测的写回洞）：解析曾在 ``model_post_init`` 里就地改写 `api_key`，而
    `write_config_to_file` 逐字段 ``getattr`` 取模板 ⇒ 不区分就会把真密钥写回文件。

    4 段归位之后：``api_key`` **本身就是原文** ⇒ 本函数与它恒等（用例 ①② 钉住这条），
    但**不是**恒等函数——没经过配置构造路径的对象仍返回 ``None``（用例③，
    写回守卫的防御分支靠它可达）。
    """

    def test_reference_is_the_raw_text_for_writeback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(FAKE_ENV_VAR, FAKE_KEY_VALUE)
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, REFERENCE_TEXT)

        config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)
        provider = config.api_providers[0]

        # 归位后：对象里的值 == 盘上原文 == 写回源（三者同一个字符串）
        assert provider.api_key == REFERENCE_TEXT
        assert raw_api_key_of(provider) == REFERENCE_TEXT

    def test_plaintext_raw_equals_value(self, tmp_path: Path) -> None:
        config_path = tmp_path / "model_config.toml"
        _write_model_config(config_path, FAKE_LITERAL_KEY)

        config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)
        provider = config.api_providers[0]

        assert raw_api_key_of(provider) == FAKE_LITERAL_KEY
        assert provider.api_key == FAKE_LITERAL_KEY

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
