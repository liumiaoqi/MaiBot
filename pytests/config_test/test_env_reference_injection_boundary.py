"""4 段 · 密钥引用化：``${VAR}`` 解析**时机**的回归测试（解析时机归位的判据①②④）。

3 段的解析写在 ``APIProvider.model_post_init`` 里、**就地改写** ``api_key`` ⇒ 配置对象里存的是
解析后的明文；而写路径（配置自动升级 / 钩子命中）恰好吃这个对象（``_build_config_template``
逐字段 ``getattr``）⇒ 任何一次 ``MODEL_CONFIG_VERSION`` 提升都会把明文写回文件。

4 段的修法：解析挪到 **adapter 读出配置后、注入客户端之前**，且只做在**传给工厂的副本**上
（唯一调用点 ``src/llm_models/model_client/base_client.py`` 的 ``get_client_class_instance``）。
本文件守的就是这条边界，四条判据各自对应一个用例组：

1. **注入边界真的解析**：注册一个探针 ``client_type``，走生产入口 ``get_client_class_instance``，
   断言工厂**收到的是解析值**；
2. **解析值不回灌配置对象**：同一轮里断言 ``api_providers[0].api_key`` **仍是引用**，
   且工厂收到的 provider **不是同一个对象**（副本语义——就地改写正是旧洞的根因）；
3. **明文路径不受影响**（双读期仍成立）：明文 provider 原样传给工厂；
4. **缺变量在注入那一刻报错**（不是静默空串），报错文本带变量名与字段路径。

夹具一律用**假值**；探针 client_type 用本文件独有名字，测完注销（不许污染全局注册表）。
"""

from pathlib import Path
from typing import ClassVar, List

import pytest

from src.config.config import MODEL_CONFIG_VERSION, ModelConfig, load_config_from_file
from src.config.model_configs import (
    APIProvider,
    ConfigEnvReferenceError,
    resolve_provider_env_references,
)
from src.llm_models.model_client.adapter_base import AdapterClient
from src.llm_models.model_client.base_client import ClientProviderRegistration, client_registry

# 变量名/值都带 4SEG 后缀：与仓库里别的测试与真值不串味
FAKE_ENV_VAR = "MAIBOT_TEST_4SEG_INJECT_API_KEY"
FAKE_KEY_VALUE = "sk-fake-4seg-inject-not-a-real-key"
FAKE_LITERAL_KEY = "sk-fake-4seg-literal-not-a-real-key"
REFERENCE_TEXT = "${" + FAKE_ENV_VAR + "}"

PROBE_CLIENT_TYPE = "probe-4seg-env-boundary"
"""探针 client_type：只在本文件注册，名字带段号防撞。"""


class ProbeClient(AdapterClient[object, object]):
    """探针客户端：**真的**继承 ``AdapterClient``（生产形态），只把工厂收到的 provider 记下来。

    ⚠️ 为什么不返回一个 ``object()`` 糊过去：``ClientRegistry`` 会按 ``client.api_provider``
    遍历缓存（注册/注销时都走一遍），返回假对象会在**别的**用例上炸出 ``AttributeError``。
    也不在这里建 ``AsyncOpenAI``——本用例要判的是"交给工厂的那个 provider 长什么样"，
    工厂是注入边界的下游第一站，与 SDK 构造看到的是同一个对象。
    """

    def __init__(self, api_provider: APIProvider) -> None:
        super().__init__(api_provider)
        self.received_api_keys.append(api_provider.api_key)

    received_api_keys: ClassVar[list[str]] = []
    """工厂收到的 api_key 序列（类级：便于按用例清空）。"""

    def get_support_image_formats(self) -> List[str]:
        """探测用：不涉及图片格式。"""
        return ["jpeg", "png"]

    def _build_default_stream_response_handler(self, request):
        raise NotImplementedError("探针不实现流式请求")

    def _build_default_response_parser(self, request):
        raise NotImplementedError("探针不实现响应解析")

    async def _execute_response_request(self, request, stream_response_handler, response_parser):
        raise NotImplementedError("探针不发请求")

    async def _execute_embedding_request(self, request):
        raise NotImplementedError("探针不发请求")

    async def _execute_audio_transcription_request(self, request):
        raise NotImplementedError("探针不发请求")


def _write_model_config(path: Path, api_key_value: str) -> None:
    """写一份最小可用的 model_config.toml（版本=当前版本，不触发自动升级改写）。"""
    path.write_text(
        f"""[inner]
version = "{MODEL_CONFIG_VERSION}"

[[models]]
model_identifier = "fake-model-4seg"
name = "fake-model-4seg"
api_provider = "FakeProvider"

[[api_providers]]
name = "FakeProvider"
base_url = "https://fake.invalid/v1"
api_key = "{api_key_value}"
auth_type = "bearer"
""",
        encoding="utf-8",
    )


def _load_provider(tmp_path: Path, api_key_value: str) -> APIProvider:
    """走生产加载路径拿到 provider（不从 ``tmp_path`` 之外读任何东西）。"""
    config_path = tmp_path / "model_config.toml"
    _write_model_config(config_path, api_key_value)
    config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)
    return config.api_providers[0]


class TestInjectionBoundary:
    """判据①②③：解析发生在工厂调用前，且**不**回灌配置对象。"""

    @pytest.fixture()
    def captured(self):
        """注册探针客户端类型，收集工厂被调用时收到的 provider（测完注销）。

        ⚠️ 为什么不 import ``openai_client`` 走真客户端：那会把 ``AsyncOpenAI`` 也建起来
        （要有 key、要联网准备），而本用例要判的是"**交给工厂的那个 provider** 长什么样"——
        工厂是注入边界的**下游第一站**，在这里取样与在 SDK 构造里取样是同一个对象
        （``base_client`` 只传一次）。
        """
        seen: list[APIProvider] = []

        def _factory(api_provider: APIProvider) -> ProbeClient:
            seen.append(api_provider)
            return ProbeClient(api_provider)

        client_registry.register_provider(
            ClientProviderRegistration(client_type=PROBE_CLIENT_TYPE, factory=_factory)
        )
        try:
            yield seen
        finally:
            # 注销走注册表本体（`ClientRegistry` 没有公开的 unregister_provider：
            # 插件那条路是 `unregister_plugin_providers`，探针没有 plugin_id 可用）
            client_registry.client_registry.pop(PROBE_CLIENT_TYPE, None)
            client_registry.client_instance_cache.pop("FakeProvider", None)
            ProbeClient.received_api_keys.clear()

    def test_factory_receives_resolved_key_while_config_object_keeps_reference(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, captured: list[APIProvider]
    ) -> None:
        """判据①②：工厂拿到明文，配置对象**仍是**引用——两个断言必须同轮出现。"""
        monkeypatch.setenv(FAKE_ENV_VAR, FAKE_KEY_VALUE)
        provider = _load_provider(tmp_path, REFERENCE_TEXT)
        assert provider.api_key == REFERENCE_TEXT  # 加载期不解析（前置条件）

        injected = provider.model_copy(update={"client_type": PROBE_CLIENT_TYPE})
        client_registry.get_client_class_instance(injected)

        assert len(captured) == 1
        handed_to_factory = captured[0]
        assert handed_to_factory.api_key == FAKE_KEY_VALUE, "注入边界没有解析引用"
        # 副本语义：不是同一个对象 ⇒ 就地改写它不可能回灌配置对象
        assert handed_to_factory is not injected
        assert injected.api_key == REFERENCE_TEXT, "解析值被写回了传进来的对象"
        # 非解析位按契约保持字面量
        assert handed_to_factory.base_url == provider.base_url

    def test_resolve_helper_is_pure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """副本语义的**最小**判据（不经注册表）：解析函数本身不改入参。"""
        monkeypatch.setenv(FAKE_ENV_VAR, FAKE_KEY_VALUE)
        provider = _load_provider(tmp_path, REFERENCE_TEXT)

        resolved = resolve_provider_env_references(provider)

        assert resolved.api_key == FAKE_KEY_VALUE
        assert resolved is not provider
        assert provider.api_key == REFERENCE_TEXT
        # 明文（非引用）⇒ 不复制，原对象返回（不为此多付一次拷贝）
        literal = _load_provider(tmp_path, FAKE_LITERAL_KEY)
        assert resolve_provider_env_references(literal) is literal

    def test_literal_path_is_untouched(self, tmp_path: Path, captured: list[APIProvider]) -> None:
        """判据④：明文路径不受影响（双读期仍成立，且连对象都不换）。"""
        provider = _load_provider(tmp_path, FAKE_LITERAL_KEY)

        injected = provider.model_copy(update={"client_type": PROBE_CLIENT_TYPE})
        client_registry.get_client_class_instance(injected)

        assert captured[0].api_key == FAKE_LITERAL_KEY
        assert injected.api_key == FAKE_LITERAL_KEY


class TestMissingVariableAtInjection:
    """判据④的另一半：缺变量**必须**报错（含变量名与字段路径），不静默退化成空串。"""

    def test_missing_variable_reports_name_and_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(FAKE_ENV_VAR, raising=False)
        provider = _load_provider(tmp_path, REFERENCE_TEXT)

        with pytest.raises(ConfigEnvReferenceError) as excinfo:
            resolve_provider_env_references(provider)

        assert excinfo.value.variable == FAKE_ENV_VAR
        assert excinfo.value.field_path == "api_providers[FakeProvider].api_key"
        assert FAKE_ENV_VAR in str(excinfo.value)

    def test_blank_variable_counts_as_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """空值/空白值算"没配"——静默给空串会被下游当成"没配 key"，排障成本高。"""
        monkeypatch.setenv(FAKE_ENV_VAR, "   ")
        provider = _load_provider(tmp_path, REFERENCE_TEXT)

        with pytest.raises(ConfigEnvReferenceError):
            resolve_provider_env_references(provider)

    def test_reference_text_provider_is_constructible_without_the_variable(self) -> None:
        """反例（防止"改回加载期解析"）：缺变量也能**构造**出引用形态的 provider。

        旧实现下这一行会直接抛 ``ConfigEnvReferenceError``（解析在 ``model_post_init``）；
        现在构造只做形状与非空校验 ⇒ 不再抛。本条是"归位"最直接的单点判据。
        """
        provider = APIProvider(
            name="FakeProvider",
            base_url="https://fake.invalid/v1",
            api_key=REFERENCE_TEXT,
            auth_type="bearer",
        )

        assert provider.api_key == REFERENCE_TEXT
