"""P2 · 密钥外部化与脱敏（判据门 ①②③）

夹具里的 api_key / token **一律是假值**：真密钥不进测试、不进入库文件。

判据门：
- ① 三种引用情形：命中 / 未命中（报错并指明变量名）/ 非引用明文（原样）
- ② 响应体 grep 不到真值（明文夹具与引用夹具都测）
- ③ 往返前后未触碰字段逐字段对账

写路径的隔离方式：只把**路由模块**的 `CONFIG_DIR` 指到 tmp_path——
不动 `src.config.config` 的全局，也不碰别人的模块（P1/P3 在改的文件一律不碰）。
"""

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
import tomlkit
from fastapi.testclient import TestClient

from src.config.config_base import AttributeData
from src.config.model_configs import APIProvider, ConfigEnvReferenceError, resolve_env_references
from src.webui import config_secrets
from src.webui.app import create_app
from src.webui.dependencies import require_auth

FAKE_LITERAL_KEY = "sk-fake-literal-0000deadbeef"
FAKE_ENV_KEY_VALUE = "sk-fake-env-0000cafebabe"
FAKE_BOT_TOKEN = "fake-bot-token-0000feedface"
FAKE_NEW_KEY = "sk-fake-new-0000abc123"
REFERENCE_ENV_VAR = "P2_FAKE_DEEPSEEK_KEY"
REFERENCE_TEXT = "${" + REFERENCE_ENV_VAR + "}"

MODEL_CONFIG_TEMPLATE = """[inner]
version = "0.9.0"

[[api_providers]]
name = "FakePlain"
base_url = "https://plain.example.invalid/v1"
api_key = "@@LITERAL@@"
client_type = "openai"
auth_type = "bearer"
auth_header_prefix = "Bearer"
model_list_endpoint = "/models"
timeout = 30
retry_interval = 5
max_retry = 2
organization = "fake-org"
project = "fake-project"

[[api_providers]]
name = "FakeRef"
base_url = "https://ref.example.invalid/v1"
api_key = "${P2_FAKE_DEEPSEEK_KEY}"
client_type = "openai"
auth_type = "bearer"
auth_header_prefix = "Bearer"
model_list_endpoint = "/models"
timeout = 45
retry_interval = 7
max_retry = 1
organization = "fake-ref-org"

[[models]]
category = "llm"
name = "fake-model"
model_identifier = "fake-model-id"
api_provider = "FakePlain"
capabilities = ["text_generation", "tool_calling"]

[model_task_config.replyer]
model_list = ["fake-model"]
max_tokens = 2048
temperature = 0.5
"""

BOT_CONFIG_TEMPLATE = f"""[inner]
version = "0.9.0"

[maim_message]
auth_token = ["{FAKE_BOT_TOKEN}"]
api_server_allowed_api_keys = []

[chat]
max_tokens = 4096
"""


def _load_plain(config_path: Any) -> Dict[str, Any]:
    """把 TOML 文件读成纯 Python 结构（对账用）。"""
    with open(config_path, "r", encoding="utf-8") as file:
        return tomlkit.load(file).unwrap()


def _assert_secret_marker(marker: Any, *, path: str, configured: bool, kind: str | None = None) -> None:
    """断言秘密占位是 F2 冻结的三态形状（2 段起）。

    2 段把占位从 ``{path, set}`` 升级成 ``{$secret, path, set, kind}``：
    ``$secret`` 让"这是秘密"成为显式声明，``kind`` 区分 ``literal``/``reference``
    （引用也是秘密——值在环境变量里，照样不出站）。``path`` 保留是 F3 的要求：
    写回时"占位自带来源路径"是认领原值的依据。

    未配置态**不带** ``kind``（没有值就没有形态可言）。
    """
    assert isinstance(marker, dict), marker
    assert marker["$secret"] is True, marker
    assert marker["path"] == path, marker
    assert marker["set"] is configured, marker
    if configured:
        assert marker["kind"] == (kind or "literal"), marker
    else:
        assert "kind" not in marker, marker


@pytest.fixture(autouse=True)
def _register_webui_ports():
    """注册 WebUI 所需 Port。

    `middleware/anti_crawler.py` 在 **import 时**就读配置（`create_app` 会触发 import），
    没有 Port 直接 AttributeError——照 tests/webui/conftest.py 的既有做法补上。
    """
    from src.core.adapters.agent_config_port import set_agent_config_provider
    from src.core.app_config_port_registry import reset_app_config_port, set_app_config_port
    from src.core.bot_config_port_registry import reset_bot_config_port, set_bot_config_port

    set_app_config_port(
        SimpleNamespace(
            get_webui_anti_crawler_mode=lambda: "off",
            get_webui_allowed_ips=lambda: [],
            get_webui_trusted_proxies=lambda: [],
            get_webui_trust_xff=lambda: False,
            get_webui_secure_cookie=lambda: False,
            get_webui_mode=lambda: "development",
            get_a_memorix_full_config=lambda: {},
        )
    )
    set_bot_config_port(
        SimpleNamespace(
            get_bot_platform=lambda: "aiocqhttp",
            get_bot_primary_account=lambda: "",
            get_bot_platforms=lambda: [],
            get_bot_nickname=lambda: "MaiBot",
            get_bot_qq_account=lambda platform: 0,
        )
    )
    set_agent_config_provider(
        SimpleNamespace(
            get_agent=lambda agent_id: None,
            list_agents=lambda: [],
            get_default_agent=lambda: None,
            has_agent=lambda agent_id: False,
            reload=lambda: None,
            reload_agent=lambda agent_id: False,
            load=lambda: None,
        )
    )
    yield
    reset_app_config_port()
    reset_bot_config_port()


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """把配置面指向 tmp_path：真配置不被读写，夹具里只有假密钥。"""
    import src.webui.routers.config as config_router
    import src.webui.routers.model as model_router

    (tmp_path / "model_config.toml").write_text(
        MODEL_CONFIG_TEMPLATE.replace("@@LITERAL@@", FAKE_LITERAL_KEY), encoding="utf-8"
    )
    (tmp_path / "bot_config.toml").write_text(BOT_CONFIG_TEMPLATE, encoding="utf-8")

    monkeypatch.setattr(config_router, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(model_router, "CONFIG_DIR", tmp_path)
    # 保存后路由会 **await** config_manager.reload_config()；测试里全局 config_manager 是 None，
    # 而真实实现是 async（src/config/config.py:489）⇒ 替身必须也是 async，
    # 否则 `await None` 会炸（2026-10-16 收尾令把全部保存路径改成 await 之后暴露）
    async def _reload(*args, **kwargs):
        return True

    monkeypatch.setattr(
        config_router,
        "config_manager",
        SimpleNamespace(reload_config=_reload),
    )
    return tmp_path


@pytest.fixture
def client(config_dir, _register_webui_ports):
    """真实 app + 假鉴权：URL 与生产一致（/api/webui/config/...）。"""
    app = create_app(enable_static=False)
    app.dependency_overrides[require_auth] = lambda: "test-token"
    with TestClient(app) as test_client:
        yield test_client


# ── 判据门 ①：三种引用情形 ──────────────────────────────────────────


class TestEnvReferenceResolution:
    """① 命中 / 未命中（报错）/ 非引用明文（原样）"""

    def test_reference_hit_reads_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        resolved = resolve_env_references(REFERENCE_TEXT, field_path="api_providers[FakeRef].api_key")

        assert resolved == FAKE_ENV_KEY_VALUE

    def test_reference_missing_raises_and_names_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(REFERENCE_ENV_VAR, raising=False)

        with pytest.raises(ConfigEnvReferenceError) as excinfo:
            resolve_env_references(REFERENCE_TEXT, field_path="api_providers[FakeRef].api_key")

        assert excinfo.value.variable == REFERENCE_ENV_VAR
        assert REFERENCE_ENV_VAR in str(excinfo.value)
        assert "api_providers[FakeRef].api_key" in str(excinfo.value)

    def test_blank_referenced_variable_is_treated_as_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """变量存在但为空 ⇒ 也算缺——空串正是"静默变空"的形态。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, "   ")

        with pytest.raises(ConfigEnvReferenceError) as excinfo:
            resolve_env_references(REFERENCE_TEXT, field_path="api_providers[FakeRef].api_key")

        assert excinfo.value.variable == REFERENCE_ENV_VAR

    def test_plaintext_value_is_returned_unchanged(self) -> None:
        assert resolve_env_references(FAKE_LITERAL_KEY, field_path="api_providers[x].api_key") == FAKE_LITERAL_KEY

    def test_unowned_dollar_braces_stay_literal(self) -> None:
        """不是合法变量名形态的 ${...} 不是本机制认领的引用，保持字面量。"""
        for raw_value in ("${}", "${1BAD}", "prefix-${", "plain-text"):
            assert resolve_env_references(raw_value, field_path="api_providers[x].api_key") == raw_value

    def test_provider_from_dict_keeps_reference_unresolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """**4 段按归位后的口径改写过**：``from_dict`` **不再**解析 ``${VAR}``。

        旧判据（``provider.api_key == FAKE_ENV_KEY_VALUE``）现在被有意反转——解析期构造对象时
        就地改写正是"升级回写把明文写回文件"的根因（3 段实测）。新判据是对象里**仍是引用**，
        解析由 ``resolve_provider_env_references`` 在注入客户端之前做（判据在
        ``pytests/config_test/test_env_reference_injection_boundary.py``）。
        """
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        provider = APIProvider.from_dict(
            AttributeData(),
            {"name": "FakeRef", "base_url": "https://x.invalid/v1", "api_key": REFERENCE_TEXT},
        )

        assert provider.api_key == REFERENCE_TEXT
        assert provider.api_key != FAKE_ENV_KEY_VALUE

    def test_provider_from_dict_missing_variable_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """**4 段按归位后的口径改写过**：缺变量在构造期**不再**报错。

        旧判据（构造即抛、消息带变量名）对应"解析在 ``model_post_init``"；归位之后构造只做
        形状与非空校验，缺变量的报错推后到**注入客户端**那一刻（那里仍带变量名与字段路径）。

        ⚠️ 行为代价（如实记录）：容器不再因为"某个变量没配"而起不来——代价是**这个引用
        在真正被用之前不会被验证**。判据：错误没丢，只是换了时机（见边界用例的双条断言）。
        """
        monkeypatch.delenv(REFERENCE_ENV_VAR, raising=False)

        provider = APIProvider.from_dict(
            AttributeData(),
            {"name": "FakeRef", "base_url": "https://x.invalid/v1", "api_key": REFERENCE_TEXT},
        )

        assert provider.api_key == REFERENCE_TEXT


# ── 脱敏口径与嵌套遍历 ──────────────────────────────────────────────


class TestRedactionCriterion:
    def test_criterion_stays_in_sync_with_request_snapshot(self) -> None:
        """防漂移：本模块的精确集必须与 request_snapshot._SENSITIVE_KEYS 同源。"""
        from src.llm_models.request_snapshot import _SENSITIVE_KEYS

        assert set(config_secrets.SENSITIVE_KEYS) == set(_SENSITIVE_KEYS)

    def test_nested_containers_are_redacted(self) -> None:
        data = {"a": {"b": [{"token": "t", "keep": 1}]}, "c": "plain"}

        redacted = config_secrets.redact_config_secrets(data)

        _assert_secret_marker(redacted["a"]["b"][0]["token"], path="a.b[0].token", configured=True)
        assert redacted["a"]["b"][0]["keep"] == 1
        assert redacted["c"] == "plain"

    def test_sensitive_container_is_replaced_whole(self) -> None:
        """敏感键的值本身是容器时整块替换——不下钻，免得子键漏值。"""
        redacted = config_secrets.redact_config_secrets({"token": {"nested": "secret-value"}})

        _assert_secret_marker(redacted["token"], path="token", configured=True)
        assert "secret-value" not in str(redacted)

    def test_blank_secret_reports_not_set(self) -> None:
        marker = config_secrets.redact_config_secrets({"api_key": "   "})["api_key"]

        _assert_secret_marker(marker, path="api_key", configured=False)

    def test_suffix_rule_covers_real_secret_fields(self) -> None:
        """精确集漏了 auth_token / allowed_api_keys —— 后缀规则补上。"""
        for key in ("auth_token", "access_token", "api_server_allowed_api_keys", "client_secret"):
            assert config_secrets.is_sensitive_key(key), key

    def test_suffix_rule_does_not_swallow_max_tokens(self) -> None:
        """反例守卫：`max_tokens` 是输出上限不是密钥，不能被误脱敏。"""
        assert not config_secrets.is_sensitive_key("max_tokens")
        assert not config_secrets.is_sensitive_key("tokenizer_mode")
        assert config_secrets.redact_config_secrets({"max_tokens": 2048})["max_tokens"] == 2048


# ── 判据门 ②：响应体里 grep 不到真值 ────────────────────────────────


class TestReadPathHidesSecrets:
    def test_fixture_really_contains_the_secrets(self, config_dir) -> None:
        """对照实验：夹具里确实有真值，否则"grep 不到"是假绿。"""
        model_text = (config_dir / "model_config.toml").read_text(encoding="utf-8")
        bot_text = (config_dir / "bot_config.toml").read_text(encoding="utf-8")

        assert FAKE_LITERAL_KEY in model_text
        assert REFERENCE_TEXT in model_text
        assert FAKE_BOT_TOKEN in bot_text

    def test_model_config_response_hides_plaintext_key(self, client: TestClient) -> None:
        response = client.get("/api/webui/config/model")

        assert response.status_code == 200, response.text
        assert FAKE_LITERAL_KEY not in response.text
        _assert_secret_marker(
            response.json()["config"]["api_providers"][0]["api_key"],
            path="api_providers[0].api_key",
            configured=True,
            kind="literal",
        )

    def test_model_config_response_hides_reference_and_env_value(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        response = client.get("/api/webui/config/model")

        assert response.status_code == 200, response.text
        assert FAKE_ENV_KEY_VALUE not in response.text
        assert REFERENCE_TEXT not in response.text
        _assert_secret_marker(
            response.json()["config"]["api_providers"][1]["api_key"],
            path="api_providers[1].api_key",
            configured=True,
            kind="reference",
        )

    def test_bot_config_response_hides_maim_message_auth_token(self, client: TestClient) -> None:
        """`maim_message.auth_token` 是真密钥，精确口径漏它——这里守后缀规则。"""
        response = client.get("/api/webui/config/bot")

        assert response.status_code == 200, response.text
        assert FAKE_BOT_TOKEN not in response.text
        _assert_secret_marker(
            response.json()["config"]["maim_message"]["auth_token"],
            path="maim_message.auth_token",
            configured=True,
            kind="literal",
        )
        assert response.json()["config"]["chat"]["max_tokens"] == 4096


# ── 判据门 ③：写路径保真（往返对账） ────────────────────────────────


class TestWritePathFidelity:
    def test_whole_config_roundtrip_keeps_key_and_unseen_fields(
        self, client: TestClient, config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """整份配置 POST 回来（另一个写入口）也要还原占位、保住没动的节。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = config_dir / "model_config.toml"
        before = _load_plain(config_path)

        # 把 GET 到的（脱敏后的）配置原样 POST 回去 = 最忠实的往返
        read_back = client.get("/api/webui/config/model").json()["config"]
        _assert_secret_marker(read_back["api_providers"][0]["api_key"], path="api_providers[0].api_key", configured=True)

        response = client.post("/api/webui/config/model", json=read_back)

        assert response.status_code == 200, response.text
        after = _load_plain(config_path)
        assert after == before, "整份往返后配置应逐字段一致"
        assert config_secrets.find_unresolved_sentinels(after) == []

    def test_section_roundtrip_preserves_untouched_fields(
        self, client: TestClient, config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = config_dir / "model_config.toml"
        before = _load_plain(config_path)

        # 1) 页面读到的就是脱敏后的配置（api_key 是占位，不是真值）
        read_back = client.get("/api/webui/config/model").json()["config"]
        providers: List[Dict[str, Any]] = read_back["api_providers"]
        assert isinstance(providers[0]["api_key"], dict)

        # 2) 页面只改了第一个提供商的 base_url；第二个提供商的条目里
        #    "页面上没展示的字段"（retry_interval / organization）故意不提交
        providers[0]["base_url"] = "https://plain.example.invalid/v2"
        del providers[1]["retry_interval"]
        del providers[1]["organization"]

        response = client.post("/api/webui/config/model/section/api_providers", json=providers)

        assert response.status_code == 200, response.text
        after = _load_plain(config_path)

        # ③-1 未触碰的节逐字段对账
        for section in ("inner", "models", "model_task_config"):
            assert after[section] == before[section], f"节 {section} 被改写"

        # ③-2 占位还原成原值：明文与 ${VAR} 引用两种都不丢
        assert after["api_providers"][0]["api_key"] == FAKE_LITERAL_KEY
        assert after["api_providers"][1]["api_key"] == REFERENCE_TEXT

        # ③-3 没提交的字段原样保留（不整段 replace）
        for key in ("retry_interval", "organization", "model_list_endpoint", "client_type", "timeout"):
            assert after["api_providers"][1][key] == before["api_providers"][1][key], key

        # ③-4 显式改动落地；占位没有写进文件
        assert after["api_providers"][0]["base_url"] == "https://plain.example.invalid/v2"
        assert config_secrets.find_unresolved_sentinels(after) == []

    def test_save_keeps_reference_when_referenced_variable_missing(
        self, client: TestClient, config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**4 段按归位后的口径改写过**：缺变量**不再**让这次保存 400。

        旧判据（400 + 变量名 + 文件不动）对应"加载/保存期解析引用"。归位之后配置侧**不认识**
        引用能否解析（那是注入边界的事）⇒ 保存照常成功，且**盘上仍是引用**（不是坏明文、
        也不是空串）。本用例改为钉住这条新语义，并显式记录 UX 变化：以前这个错误在校验器里
        被大声报出来，现在要等到真正建客户端时才报——**代价是有意接受的**（参见
        `test_env_reference_injection_boundary.py`：错误没丢，只是换了时机）。

        ⚠️ 这条用例是"三对照"里**保留**那对照的一部分：缺变量的引用必须**原样活着**，
        既不能被换成空串，也不能被换成明文。
        """
        monkeypatch.delenv(REFERENCE_ENV_VAR, raising=False)
        config_path = config_dir / "model_config.toml"
        providers = client.get("/api/webui/config/model").json()["config"]["api_providers"]

        response = client.post("/api/webui/config/model/section/api_providers", json=providers)

        assert response.status_code == 200, response.text
        after = _load_plain(config_path)
        keys = [provider["api_key"] for provider in after["api_providers"]]
        assert REFERENCE_TEXT in keys, f"缺变量的引用没能原样保留在盘上：{keys}"
        assert "" not in keys, "引用被静默换成了空串（正是 P2 要防的形态）"

    def test_new_plaintext_key_is_written(
        self, client: TestClient, config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """用户在页面上重新填的明文密钥要能写进去（脱敏不挡正常写入）。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = config_dir / "model_config.toml"
        providers = client.get("/api/webui/config/model").json()["config"]["api_providers"]
        providers[1]["api_key"] = FAKE_NEW_KEY

        response = client.post("/api/webui/config/model/section/api_providers", json=providers)

        assert response.status_code == 200, response.text
        assert _load_plain(config_path)["api_providers"][1]["api_key"] == FAKE_NEW_KEY

    def test_sentinel_without_origin_is_refused_not_guessed(
        self, client: TestClient, config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """凭空构造的占位（来源下标不存在）：拒绝落盘，而不是按位置猜一把。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = config_dir / "model_config.toml"
        before_bytes = config_path.read_bytes()
        ghost_provider = [
            {
                "name": "Ghost",
                "base_url": "https://ghost.invalid/v1",
                "api_key": {"path": "api_providers[9].api_key", "set": True},
            }
        ]

        response = client.post("/api/webui/config/model/section/api_providers", json=ghost_provider)

        assert response.status_code == 400, response.text
        assert "api_providers[9].api_key" in response.text
        assert config_path.read_bytes() == before_bytes

    def test_renamed_provider_keeps_its_own_key(
        self, client: TestClient, config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """改名 + 条目换序：占位自带来源下标，密钥不会串到别的提供商身上。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = config_dir / "model_config.toml"
        providers = client.get("/api/webui/config/model").json()["config"]["api_providers"]

        # 换序（1 号位在前）+ 给 1 号位的提供商改名
        reordered = [providers[1], providers[0]]
        reordered[0]["name"] = "FakeRefRenamed"

        response = client.post("/api/webui/config/model/section/api_providers", json=reordered)

        assert response.status_code == 200, response.text
        after = _load_plain(config_path)["api_providers"]
        renamed = next(provider for provider in after if provider["name"] == "FakeRefRenamed")
        renamed_neighbour = next(provider for provider in after if provider["name"] == "FakePlain")
        assert renamed["api_key"] == REFERENCE_TEXT
        assert renamed_neighbour["api_key"] == FAKE_LITERAL_KEY
