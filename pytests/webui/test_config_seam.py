"""2 段 · 接缝换形（判据门 ①②③④）

夹具里的密钥**一律是假值**：真密钥不进测试、不进入库文件。

判据门：
- ① 并发写冲突可检出：两个"读到同一 revision"的写者 ⇒ 后者 409 + 双 revision
- ② 未触碰字段往返存活：整平面往返 + 单节往返（明文与 ``${VAR}`` 引用两种秘密各一），逐字段对账
- ③ 秘密不出站：响应体 grep 不到真值；**同时**非秘密字段没有被过度脱敏
- ④ 重置语义：``unset(path)`` 后 ``inherited=true``（不是"写了个等于默认的值"）

隔离方式与 ``test_config_secrets.py`` 一致：只把**配置面**指向 tmp_path，
不动 ``src.config.config`` 的全局，也不碰别人的模块。
"""

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
import tomlkit
from fastapi.testclient import TestClient

from src.config.config import Config
from src.webui import config_secrets, config_store
from src.webui.app import create_app
from src.webui.config_paths import WILDCARD, parse_declaration
from src.webui.dependencies import require_auth

FAKE_LITERAL_KEY = "sk-fake-seam-literal-0000deadbeef"
FAKE_ENV_KEY_VALUE = "sk-fake-seam-env-0000cafebabe"
FAKE_BOT_TOKEN = "fake-seam-bot-token-0000feedface"
FAKE_ALLOWED_KEY = "fake-seam-allowed-key-0000badc0de"
FAKE_NEW_KEY = "sk-fake-seam-new-0000abc123"
REFERENCE_ENV_VAR = "P2_SEAM_FAKE_DEEPSEEK_KEY"
REFERENCE_TEXT = "${" + REFERENCE_ENV_VAR + "}"

READ_URL = "/api/webui/config/get"
MUTATE_URL = "/api/webui/config/mutate"

MODEL_CONFIG_TEMPLATE = f"""\
[inner]
version = "0.9.0"

[[api_providers]]
name = "SeamPlain"
base_url = "https://plain.example.invalid/v1"
api_key = "{FAKE_LITERAL_KEY}"
client_type = "openai"
auth_type = "bearer"
auth_header_prefix = "Bearer"
model_list_endpoint = "/models"
timeout = 30
retry_interval = 5
max_retry = 2
organization = "seam-org"
project = "seam-project"

[[api_providers]]
name = "SeamRef"
base_url = "https://ref.example.invalid/v1"
api_key = "{REFERENCE_TEXT}"
client_type = "openai"
auth_type = "bearer"
auth_header_prefix = "Bearer"
model_list_endpoint = "/models"
timeout = 45
retry_interval = 7
max_retry = 1
organization = "seam-ref-org"

[[models]]
category = "llm"
name = "seam-model"
model_identifier = "seam-model-id"
api_provider = "SeamPlain"
capabilities = ["text_generation", "tool_calling"]

[model_task_config.replyer]
model_list = ["seam-model"]
max_tokens = 2048
temperature = 0.5
"""

BOT_CONFIG_TEMPLATE = f"""\
[inner]
version = "0.9.0"

[bot]
qq_account = "10001"
nickname = "SeamBot"

[chat]
max_context_size = 42

[maim_message]
auth_token = ["{FAKE_BOT_TOKEN}"]
enable_api_server = true
api_server_allowed_api_keys = ["{FAKE_ALLOWED_KEY}"]
"""


def _load_plain(config_path: Any) -> Dict[str, Any]:
    """把 TOML 文件读成纯 Python 结构（逐字段对账用）。"""
    with open(config_path, "r", encoding="utf-8") as file:
        return tomlkit.load(file).unwrap()


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
def seam_config_dir(tmp_path, monkeypatch):
    """把配置面指向 tmp_path：真配置不被读写，夹具里只有假密钥。

    ⚠️ revision 状态是**进程内存**里的模块级字典，必须逐用例复位——
    否则上一个用例推进过的计数会漏到下一个用例，测试之间就不再独立。
    """
    import src.webui.routers.config as config_router
    import src.webui.routers.model as model_router

    (tmp_path / "model_config.toml").write_text(MODEL_CONFIG_TEMPLATE, encoding="utf-8")
    (tmp_path / "bot_config.toml").write_text(BOT_CONFIG_TEMPLATE, encoding="utf-8")

    monkeypatch.setattr(config_router, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(model_router, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_store, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_store, "_REVISION_STATES", {})
    # 保存后路由会调 config_manager.reload_config()；测试里全局 config_manager 是 None
    monkeypatch.setattr(
        config_router,
        "config_manager",
        SimpleNamespace(reload_config=lambda *args, **kwargs: None),
    )
    return tmp_path


@pytest.fixture
def client(seam_config_dir):
    """真实 app + 假鉴权：URL 与生产一致（/api/webui/config/...）。"""
    app = create_app(enable_static=False)
    app.dependency_overrides[require_auth] = lambda: "test-token"
    with TestClient(app) as test_client:
        yield test_client


def _read_paths(client: TestClient, namespace: str, paths: List[str] | None = None) -> Dict[str, Any]:
    """调读接缝，返回整个响应体（断言要用 revision 与 entries）。"""
    response = client.post(READ_URL, json={"namespace": namespace, "paths": paths or []})
    assert response.status_code == 200, response.text
    return response.json()


def _entries_by_path(body: Dict[str, Any]) -> Dict[str, Any]:
    return {entry["path"]: entry for entry in body["entries"]}


def _mutate(
    client: TestClient,
    namespace: str,
    revision: int,
    ops: List[Dict[str, Any]],
    *,
    revision_key: str = "expectedRevision",
) -> Any:
    return client.post(
        MUTATE_URL,
        json={"namespace": namespace, revision_key: revision, "ops": ops},
    )


# ── 判据门 ①：并发写冲突可检出 ──────────────────────────────────────


class TestConcurrentWriteConflict:
    def test_second_writer_with_same_revision_is_rejected(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """两个写者"读到同一 revision" ⇒ 后者被拒（409 + 双 revision），且没写进去。"""
        config_path = seam_config_dir / "bot_config.toml"
        revision = _read_paths(client, "bot", ["chat.max_context_size"])["revision"]

        first = _mutate(
            client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 43}]
        )
        assert first.status_code == 200, first.text
        assert first.json()["revision"] == revision + 1, "成功写入必须推进 revision"

        second = _mutate(
            client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 99}]
        )
        assert second.status_code == 409, second.text
        body = second.json()
        assert body["error_code"] == "BIZ_STATE_CONFLICT"
        assert body["details"]["namespace"] == "bot"
        assert body["details"]["expected_revision"] == revision
        assert body["details"]["current_revision"] == revision + 1

        # 冲突的写入**一个字节都不该落盘**（不自动合并、不静默覆盖）
        assert _load_plain(config_path)["chat"]["max_context_size"] == 43

    def test_retry_after_rereading_succeeds(self, client: TestClient, seam_config_dir) -> None:
        """冲突不是死锁：重新读一次拿到新 revision，再提交就过。"""
        revision = _read_paths(client, "bot", ["chat.max_context_size"])["revision"]
        assert _mutate(client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 43}]).status_code == 200
        assert _mutate(client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 99}]).status_code == 409

        fresh_revision = _read_paths(client, "bot", ["chat.max_context_size"])["revision"]
        retried = _mutate(
            client, "bot", fresh_revision, [{"op": "set", "path": "chat.max_context_size", "value": 44}]
        )
        assert retried.status_code == 200, retried.text
        assert _load_plain(seam_config_dir / "bot_config.toml")["chat"]["max_context_size"] == 44

    def test_out_of_band_write_also_invalidates_the_revision(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """**锁不是内存计数器的自娱自乐**：raw 端点绕过新接缝改文件，旧 revision 同样作废。"""
        revision = _read_paths(client, "bot", ["chat.max_context_size"])["revision"]

        raw_body = (seam_config_dir / "bot_config.toml").read_text(encoding="utf-8").replace(
            "max_context_size = 42", "max_context_size = 50"
        )
        raw_write = client.post("/api/webui/config/bot/raw", json={"raw_content": raw_body})
        assert raw_write.status_code == 200, raw_write.text

        assert config_store.current_revision("bot") == revision + 1, "外部改动必须被识别成新版本"

        stale = _mutate(
            client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 99}]
        )
        assert stale.status_code == 409, stale.text
        assert _load_plain(seam_config_dir / "bot_config.toml")["chat"]["max_context_size"] == 50

    def test_expected_revision_is_required(self, client: TestClient) -> None:
        """F5：写**必须**带 expectedRevision——可省略的锁等于没有锁。"""
        response = client.post(
            MUTATE_URL,
            json={"namespace": "bot", "ops": [{"op": "set", "path": "chat.max_context_size", "value": 1}]},
        )
        assert response.status_code == 422, response.text

    def test_revision_survives_repeated_reads(self, client: TestClient) -> None:
        """没人写过 ⇒ 连读两次拿到同一个 revision（不制造假冲突）。"""
        assert _read_paths(client, "bot")["revision"] == _read_paths(client, "bot")["revision"]


# ── 判据门 ②：未触碰字段往返存活 ────────────────────────────────────


class TestUntouchedFieldsSurviveRoundTrip:
    def test_whole_plane_roundtrip_is_field_exact(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """整平面往返：读回全部路径 → 原样写回 → **逐字段对账**，一个字段都不许漂。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        before = _load_plain(seam_config_dir / "model_config.toml")

        read_body = _read_paths(client, "model")
        ops = [{"op": "set", "path": entry["path"], "value": entry["value"]} for entry in read_body["entries"]]
        assert ops, "整平面读必须给出条目，否则这个往返是空跑"

        written = _mutate(client, "model", read_body["revision"], ops)
        assert written.status_code == 200, written.text

        after = _load_plain(seam_config_dir / "model_config.toml")
        assert after == before, "整平面往返后配置应逐字段一致"
        _assert_no_field_drift(before, after)

    def test_section_roundtrip_keeps_untouched_fields_and_both_secret_forms(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """单节往返：只提交服务商节里被改动的路径；明文与 ``${VAR}`` 两种秘密都不丢。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"
        before = _load_plain(config_path)

        entries = _entries_by_path(_read_paths(client, "model"))
        providers_ops = [
            {"op": "set", "path": path, "value": entry["value"]}
            for path, entry in entries.items()
            if path.startswith("api_providers[0].")
        ]
        # 只改一个字段：base_url（其余路径原样回填，页面上"没展示的字段"干脆不提交）
        providers_ops = [op for op in providers_ops if op["path"] != "api_providers[0].base_url"]
        providers_ops.append(
            {"op": "set", "path": "api_providers[0].base_url", "value": "https://plain.example.invalid/v2"}
        )

        revision = _read_paths(client, "model")["revision"]
        written = _mutate(client, "model", revision, providers_ops)
        assert written.status_code == 200, written.text

        after = _load_plain(config_path)
        # ②-1 未触碰的节逐字段对账
        for section in ("inner", "models", "model_task_config"):
            assert after[section] == before[section], f"节 {section} 被改写"
        # ②-2 秘密两种形态都还在原样
        assert after["api_providers"][0]["api_key"] == FAKE_LITERAL_KEY
        assert after["api_providers"][1]["api_key"] == REFERENCE_TEXT
        # ②-3 第二个服务商整条不动（它的字段一条 op 都没提交）
        assert after["api_providers"][1] == before["api_providers"][1]
        # ②-4 显式改动落地
        assert after["api_providers"][0]["base_url"] == "https://plain.example.invalid/v2"

    def test_legacy_whole_file_roundtrip_still_holds(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """遗留整份端点（5 段才拆）在本次改造后仍要守住"往返逐字段一致"。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"
        before = _load_plain(config_path)

        read_back = client.get("/api/webui/config/model").json()["config"]
        response = client.post("/api/webui/config/model", json=read_back)
        assert response.status_code == 200, response.text

        assert _load_plain(config_path) == before

    def test_remove_at_deletes_the_element_instead_of_writing_null(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``remove_at``：真删数组元素，**不用 set null 代替**（F1）。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"
        before = _load_plain(config_path)
        revision = _read_paths(client, "model")["revision"]

        written = _mutate(
            client,
            "model",
            revision,
            [{"op": "remove_at", "path": "api_providers", "index": 1}],
        )
        assert written.status_code == 200, written.text

        after = _load_plain(config_path)
        assert len(after["api_providers"]) == len(before["api_providers"]) - 1
        assert [provider["name"] for provider in after["api_providers"]] == ["SeamPlain"]
        # 不是"留了个 null 元素"
        assert all(provider is not None for provider in after["api_providers"])

    def test_remove_at_needs_an_index(self, client: TestClient, seam_config_dir) -> None:
        revision = _read_paths(client, "model")["revision"]
        response = _mutate(client, "model", revision, [{"op": "remove_at", "path": "api_providers"}])
        assert response.status_code == 400, response.text
        assert "index" in response.text


def _assert_no_field_drift(before: Any, after: Any, prefix: str = "") -> None:
    """逐字段对账（比 ``==`` 给出更具体的位置——漂了要说清漂在哪）。"""
    if isinstance(before, dict) and isinstance(after, dict):
        assert set(before) == set(after), f"{prefix} 键集合不同：{set(before) ^ set(after)}"
        for key in before:
            _assert_no_field_drift(before[key], after[key], f"{prefix}.{key}")
        return
    if isinstance(before, list) and isinstance(after, list):
        assert len(before) == len(after), f"{prefix} 长度不同"
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            _assert_no_field_drift(left, right, f"{prefix}[{index}]")
        return
    assert before == after, f"{prefix} 值不同：{before!r} != {after!r}"


# ── 判据门 ③：秘密不出站 + 非秘密不被过度脱敏 ────────────────────────


class TestSecretsNeverLeave:
    def test_fixture_really_contains_the_secrets(self, seam_config_dir) -> None:
        """对照实验：夹具里确实有真值，否则"grep 不到"是假绿。"""
        model_text = (seam_config_dir / "model_config.toml").read_text(encoding="utf-8")
        bot_text = (seam_config_dir / "bot_config.toml").read_text(encoding="utf-8")

        assert FAKE_LITERAL_KEY in model_text
        assert REFERENCE_TEXT in model_text
        assert FAKE_BOT_TOKEN in bot_text
        assert FAKE_ALLOWED_KEY in bot_text

    def test_read_seam_never_returns_any_secret_value(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """新读接缝（整平面）里 grep 不到任何真值——明文、引用文本、环境变量的值都算。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        model_response = client.post(READ_URL, json={"namespace": "model", "paths": []})
        bot_response = client.post(READ_URL, json={"namespace": "bot", "paths": []})
        assert model_response.status_code == 200, model_response.text
        assert bot_response.status_code == 200, bot_response.text

        for leaked in (FAKE_LITERAL_KEY, REFERENCE_TEXT, FAKE_ENV_KEY_VALUE, REFERENCE_ENV_VAR):
            assert leaked not in model_response.text, f"模型配置响应里出现了 {leaked!r}"
        for leaked in (FAKE_BOT_TOKEN, FAKE_ALLOWED_KEY):
            assert leaked not in bot_response.text, f"主程序配置响应里出现了 {leaked!r}"

    def test_secret_descendant_request_does_not_leak(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """⚠️ 泄漏面：``auth_token`` 是**数组**，"列叶"会摊出 ``auth_token[0]``。

        直接按元素下标请求时，必须沿着祖先链认出它是秘密字段内部（否则这条路径会以
        "非秘密"的身份把令牌原文发出去）。
        """
        response = client.post(
            READ_URL,
            json={"namespace": "bot", "paths": ["maim_message.auth_token[0]"]},
        )
        assert response.status_code == 200, response.text
        assert FAKE_BOT_TOKEN not in response.text

        entry = _entries_by_path(response.json())["maim_message.auth_token[0]"]
        assert entry["value"]["$secret"] is True
        assert entry["value"]["path"] == "maim_message.auth_token", "标记要指出真正的秘密根"

    def test_whole_plane_read_has_no_element_level_secret_entries(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """整平面读里，秘密字段**只以字段自身**出现一次，不会以 ``[0]`` 元素形态漏出去。"""
        entries = _entries_by_path(_read_paths(client, "bot"))
        assert "maim_message.auth_token" in entries
        assert not [path for path in entries if path.startswith("maim_message.auth_token[")]
        assert not [path for path in entries if path.startswith("maim_message.api_server_allowed_api_keys[")]

    def test_secret_marker_is_the_frozen_three_state_shape(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """F2 三态：已配置给 ``kind``，未配置给 ``set: false``（且不带 ``kind``）。"""
        entries = _entries_by_path(_read_paths(client, "bot"))

        auth_token = entries["maim_message.auth_token"]["value"]
        assert auth_token["$secret"] is True
        assert auth_token["set"] is True
        assert auth_token["kind"] == "literal"
        assert auth_token["path"] == "maim_message.auth_token"

        allowed_keys = entries["maim_message.api_server_allowed_api_keys"]["value"]
        assert allowed_keys["$secret"] is True
        assert allowed_keys["set"] is True
        assert allowed_keys["kind"] == "literal"

    def test_unset_secret_reports_the_middle_state(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """三态里的**未配置**态：文件里没有这个键，也要主动报告（``set: false``）。"""
        config_path = seam_config_dir / "bot_config.toml"
        text = config_path.read_text(encoding="utf-8").replace(
            f'api_server_allowed_api_keys = ["{FAKE_ALLOWED_KEY}"]\n', ""
        )
        config_path.write_text(text, encoding="utf-8")

        entries = _entries_by_path(_read_paths(client, "bot"))
        marker = entries["maim_message.api_server_allowed_api_keys"]["value"]
        assert marker["$secret"] is True
        assert marker["set"] is False
        assert "kind" not in marker, "未配置就没有形态可言"

    def test_reference_secret_is_reported_as_reference_not_resolved(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``kind: "reference"``：值在环境变量里。

        **引用也是秘密**——读路径既不给引用文本，更不给解析后的明文（F2/F4 是两件事）。
        """
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        entries = _entries_by_path(_read_paths(client, "model"))
        reference_marker = entries["api_providers[1].api_key"]["value"]
        assert reference_marker["kind"] == "reference"
        assert reference_marker["set"] is True
        assert reference_marker["path"] == "api_providers[1].api_key"
        assert reference_marker["origin_name"] == "SeamRef"

        literal_marker = entries["api_providers[0].api_key"]["value"]
        assert literal_marker["kind"] == "literal"

    def test_there_is_no_redact_switch(self, client: TestClient, seam_config_dir) -> None:
        """F2：读路径**不带 redact 开关**——带上也没用，出站一律脱敏。"""
        for query in ("", "?redact=false", "?redact=0", "?include_secrets=true"):
            response = client.post(f"{READ_URL}{query}", json={"namespace": "bot", "paths": []})
            assert response.status_code == 200, response.text
            assert FAKE_BOT_TOKEN not in response.text, f"查询串 {query!r} 把脱敏关掉了"

    def test_legacy_read_endpoints_use_the_schema_declaration(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """遗留端点也跟着新的判据走（``auth_token`` 由字段声明认出，不靠名字猜）。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        assert FAKE_BOT_TOKEN not in client.get("/api/webui/config/bot").text
        assert FAKE_LITERAL_KEY not in client.get("/api/webui/config/model").text
        assert REFERENCE_TEXT not in client.get("/api/webui/config/model").text

    def test_non_secret_fields_are_not_over_redacted(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """反例守卫：``max_tokens`` 是输出上限不是密钥，必须原样返回。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        model_entries = _entries_by_path(_read_paths(client, "model"))
        assert model_entries["model_task_config.replyer.max_tokens"]["value"] == 2048
        assert model_entries["model_task_config.replyer.temperature"]["value"] == 0.5
        assert model_entries["api_providers[0].timeout"]["value"] == 30
        assert model_entries["api_providers[0].organization"]["value"] == "seam-org"

        bot_entries = _entries_by_path(_read_paths(client, "bot"))
        assert bot_entries["chat.max_context_size"]["value"] == 42
        assert bot_entries["bot.nickname"]["value"] == "SeamBot"
        assert bot_entries["maim_message.enable_api_server"]["value"] is True

    def test_legacy_endpoint_does_not_over_redact(self, client: TestClient) -> None:
        """遗留整份读里，非秘密字段仍是原值（不是被整块换成标记）。"""
        config = client.get("/api/webui/config/model").json()["config"]

        assert config["model_task_config"]["replyer"]["max_tokens"] == 2048
        assert config["api_providers"][0]["organization"] == "seam-org"
        assert isinstance(config["api_providers"][0]["api_key"], dict)


# ── 判据门 ④：重置语义（unset ⇒ 继承） ───────────────────────────────


class TestResetSemantics:
    def test_unset_removes_the_key_and_reports_inherited(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """``unset`` 后 ``inherited=true``，值来自 schema 默认——**不是**写了个等于默认的值。"""
        config_path = seam_config_dir / "bot_config.toml"
        assert _load_plain(config_path)["chat"]["max_context_size"] == 42

        revision = _read_paths(client, "bot", ["chat.max_context_size"])["revision"]
        written = _mutate(client, "bot", revision, [{"op": "unset", "path": "chat.max_context_size"}])
        assert written.status_code == 200, written.text

        # ④-1 文件里**真的没有这个键**了
        after = _load_plain(config_path)
        assert "max_context_size" not in after["chat"], "unset 必须真删键，不能写默认值占位"

        # ④-2 读回来：inherited=true，值是 schema 默认（ChatConfig.max_context_size 默认 40）
        entry = _entries_by_path(_read_paths(client, "bot", ["chat.max_context_size"]))["chat.max_context_size"]
        assert entry["inherited"] is True
        assert entry["value"] == 40

    def test_writing_the_default_value_is_a_different_state(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """对照实验（防止 ④ 的判据自我循环）：显式写入等于默认值的值 ⇒ ``inherited=false``。

        如果 ``inherited`` 是"值等不等于默认值"算出来的，这条会跟上面那条一样，判据就废了。
        """
        config_path = seam_config_dir / "bot_config.toml"
        revision = _read_paths(client, "bot", ["chat.max_context_size"])["revision"]
        written = _mutate(
            client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 40}]
        )
        assert written.status_code == 200, written.text

        assert _load_plain(config_path)["chat"]["max_context_size"] == 40, "值写进去了"
        entry = _entries_by_path(_read_paths(client, "bot", ["chat.max_context_size"]))["chat.max_context_size"]
        assert entry["value"] == 40
        assert entry["inherited"] is False, "显式配过就是被覆盖了——哪怕值恰好等于默认值"

    def test_unset_secret_falls_back_to_not_configured(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """秘密字段 ``unset`` 之后回到三态的"未配置"，而不是留一个空数组占位。"""
        config_path = seam_config_dir / "bot_config.toml"
        revision = _read_paths(client, "bot", ["maim_message.auth_token"])["revision"]
        written = _mutate(client, "bot", revision, [{"op": "unset", "path": "maim_message.auth_token"}])
        assert written.status_code == 200, written.text

        assert "auth_token" not in _load_plain(config_path)["maim_message"]
        entry = _entries_by_path(_read_paths(client, "bot", ["maim_message.auth_token"]))["maim_message.auth_token"]
        assert entry["inherited"] is True
        assert entry["value"]["set"] is False

    def test_unset_a_missing_path_is_refused(self, client: TestClient, seam_config_dir) -> None:
        """重置一个本来就不存在的键 ⇒ 400（不是静默成功）。"""
        revision = _read_paths(client, "bot")["revision"]
        response = _mutate(client, "bot", revision, [{"op": "unset", "path": "chat.ascii_column_width"}])
        assert response.status_code == 400, response.text


# ── 接缝自身的边界 ─────────────────────────────────────────────────


class TestSeamBoundaries:
    def test_unknown_namespace_is_a_client_error(self, client: TestClient) -> None:
        assert client.post(READ_URL, json={"namespace": "nope", "paths": []}).status_code == 400
        revision = 1
        assert _mutate(client, "nope", revision, [{"op": "set", "path": "a", "value": 1}]).status_code == 400

    def test_unknown_path_read_is_a_client_error(self, client: TestClient, seam_config_dir) -> None:
        response = client.post(READ_URL, json={"namespace": "bot", "paths": ["chat.not_a_field"]})
        assert response.status_code == 400, response.text
        assert "chat.not_a_field" in response.text

    def test_snake_case_expected_revision_is_accepted(self, client: TestClient, seam_config_dir) -> None:
        """请求字段同时收 ``expectedRevision`` 与 ``expected_revision``（少一次联调猜谜）。"""
        revision = _read_paths(client, "bot")["revision"]
        response = _mutate(
            client,
            "bot",
            revision,
            [{"op": "set", "path": "chat.max_context_size", "value": 41}],
            revision_key="expected_revision",
        )
        assert response.status_code == 200, response.text

    def test_secret_placeholder_roundtrip_keeps_the_original_value(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F3 认领：把读回来的占位原样写回 ⇒ 原值（明文 / 引用文本）原样留在盘上。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"

        entries = _entries_by_path(_read_paths(client, "model"))
        ops = [
            {"op": "set", "path": "api_providers[0].api_key", "value": entries["api_providers[0].api_key"]["value"]},
            {"op": "set", "path": "api_providers[1].api_key", "value": entries["api_providers[1].api_key"]["value"]},
        ]
        revision = _read_paths(client, "model")["revision"]
        written = _mutate(client, "model", revision, ops)
        assert written.status_code == 200, written.text

        after = _load_plain(config_path)["api_providers"]
        assert after[0]["api_key"] == FAKE_LITERAL_KEY
        assert after[1]["api_key"] == REFERENCE_TEXT, "引用文本不能被解析后写回（那会抹掉迁移）"

    def test_reference_text_is_never_resolved_into_the_stored_file(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⚠️ 迁移破坏守卫：``${VAR}`` 必须原样留在盘上，**解析后的明文绝不能写回**。

        模型校验会把引用解析成明文——那是 F4 在**内存里**的事。写盘用的是 tomlkit 文档本身，
        不经过模型对象；否则一次跟密钥无关的保存就会把密钥迁移静默抹掉
        （3 段报的那类缺陷，本接缝必须自己不引入）。
        """
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"
        revision = _read_paths(client, "model")["revision"]

        written = _mutate(
            client,
            "model",
            revision,
            [{"op": "set", "path": "model_task_config.replyer.max_tokens", "value": 4096}],
        )
        assert written.status_code == 200, written.text

        text = config_path.read_text(encoding="utf-8")
        assert REFERENCE_TEXT in text, "引用文本必须原样留在盘上"
        assert FAKE_ENV_KEY_VALUE not in text, "解析后的明文落到盘上 = 密钥迁移被抹掉"

    def test_unclaimable_secret_placeholder_is_refused(self, client: TestClient, seam_config_dir) -> None:
        """F3 规则③：认不到来源 ⇒ **拒绝整次写入**（400 + 指明位置），绝不按位置猜。"""
        config_path = seam_config_dir / "model_config.toml"
        before_bytes = config_path.read_bytes()
        revision = _read_paths(client, "model")["revision"]

        ghost = _mutate(
            client,
            "model",
            revision,
            [
                {
                    "op": "set",
                    "path": "api_providers[0].api_key",
                    "value": {"$secret": True, "set": True, "path": "api_providers[9].api_key"},
                },
                {"op": "set", "path": "api_providers[0].timeout", "value": 99},
            ],
        )
        assert ghost.status_code == 400, ghost.text
        assert "api_providers[9].api_key" in ghost.text
        assert config_path.read_bytes() == before_bytes, "认领失败必须整次写入作废"

    def test_new_literal_secret_is_written(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """用户在页面上重新填的明文密钥要能写进去（脱敏不挡正常写入）。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"
        revision = _read_paths(client, "model")["revision"]

        written = _mutate(
            client,
            "model",
            revision,
            [{"op": "set", "path": "api_providers[1].api_key", "value": FAKE_NEW_KEY}],
        )
        assert written.status_code == 200, written.text
        assert _load_plain(config_path)["api_providers"][1]["api_key"] == FAKE_NEW_KEY

    def test_invalid_value_is_refused_without_touching_the_file(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """校验不通过 ⇒ 400，且**文件一个字节不动、revision 不前进**。"""
        config_path = seam_config_dir / "model_config.toml"
        before_bytes = config_path.read_bytes()
        revision = _read_paths(client, "model")["revision"]

        response = _mutate(
            client,
            "model",
            revision,
            [{"op": "set", "path": "api_providers[0].timeout", "value": "不是数字"}],
        )
        assert response.status_code == 400, response.text
        assert config_path.read_bytes() == before_bytes
        assert config_store.current_revision("model") == revision

    def test_empty_ops_is_refused(self, client: TestClient, seam_config_dir) -> None:
        revision = _read_paths(client, "bot")["revision"]
        assert _mutate(client, "bot", revision, []).status_code == 422


# ── 秘密判定通道的自检（声明表 / 派生 / 过渡层 / 与 F4 的对拍） ────────


def _concrete_tokens(declared_path: str) -> tuple[Any, ...]:
    """声明路径去掉通配符后的具体 token（查模型用；通配符不是模型里的一层）。"""
    return tuple(token for token in parse_declaration(declared_path) if token is not WILDCARD)


class TestSecretDeclarationChannels:
    """F2 的判据通道：字段声明（权威）+ 声明表（过渡与兜底）。"""

    def test_declared_paths_resolve_to_real_fields(self) -> None:
        """防死声明：声明表里每条路径都必须能在模型里落到真字段（否则它永远不会命中）。"""
        for namespace in sorted(config_store.NAMESPACES):
            for declared_path in sorted(config_store.secret_field_paths(namespace)):
                info = config_store.schema_field_info(namespace, _concrete_tokens(declared_path))
                assert info is not None, f"{namespace}:{declared_path} 在模型里找不到对应字段"

    def test_field_declaration_is_a_live_channel(self) -> None:
        """派生通道活着：字段声明处标了 ``x-secret`` 的，必须自动进集合。

        ``maim_message.auth_token`` 正是本轮黑名单漏掉的那一个——它现在由**字段自己**声明。
        """
        derived = config_secrets.derive_secret_field_paths(Config)

        assert "maim_message.auth_token" in derived
        assert "maim_message.api_server_allowed_api_keys" in derived

    def test_secret_set_is_declaration_plus_derivation(self) -> None:
        """并集口径：派生通道与声明表谁有都算，**派生优先**（关键是没有"谁覆盖谁"的歧义）。"""
        declared_only = config_secrets.collect_secret_field_paths("bot", None)
        # 派生通道也能认出那两个（字段已声明）⇒ 取并集后不减少
        assert declared_only == config_secrets.collect_secret_field_paths("bot", Config)

    def test_transitional_layer_coverage_is_empty_for_the_known_config(
        self, seam_config_dir
    ) -> None:
        """**过渡层台账**：本夹具里"只有后缀层兜住、没有任何声明"的键应当为空。

        这就是过渡层何时能拆的证据——哪天这张表空了（且全仓配置都是这样），
        ``is_sensitive_key`` 就可以删掉；它不为空说明还有密钥字段没被声明。
        """
        bot_declared = config_store.secret_field_paths("bot")
        model_declared = config_store.secret_field_paths("model")

        assert config_secrets.undeclared_transitional_keys(
            _load_plain(seam_config_dir / "bot_config.toml"), bot_declared
        ) == []
        assert config_secrets.undeclared_transitional_keys(
            _load_plain(seam_config_dir / "model_config.toml"), model_declared
        ) == []

    def test_transitional_layer_still_catches_an_undeclared_secret_key(self) -> None:
        """反例守卫：过渡层还在干活——没人声明的 ``some_new_credential_token`` 依然不出站。

        （这条不是判据，是"过渡层为什么还不能删"的证据；等 schema 声明铺满再删。）
        """
        data = {"some_new_credential_token": "leaked-if-you-remove-the-net"}

        redacted = config_secrets.redact_config_secrets(data, secret_paths=())

        assert "leaked-if-you-remove-the-net" not in str(redacted)
        assert config_secrets.undeclared_transitional_keys(data, ()) == ["some_new_credential_token"]


class TestReferenceKindAgreesWithF4:
    """``kind`` 的判据与 3 段（F4）的 ``${VAR}`` 语法**对拍**。

    本模块不 import 她的私有正则（那个名字她有权改），而是拿她的**公开函数**当判据：
    同语法 ⇒ 她解得出来；不是本机制认领的形态 ⇒ 她原样返回。
    """

    PROBE_ENV_VAR = "P2_SEAM_PROBE_KEY"
    PROBE_VALUE = "probe-value-0000"

    def test_pure_reference_is_the_syntax_f4_resolves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.model_configs import resolve_env_references

        monkeypatch.setenv(self.PROBE_ENV_VAR, self.PROBE_VALUE)
        text = "${" + self.PROBE_ENV_VAR + "}"

        assert config_secrets.is_env_reference_text(text)
        assert resolve_env_references(text, field_path="probe") == self.PROBE_VALUE

    def test_forms_f4_does_not_own_are_not_pure_references(self) -> None:
        from src.config.model_configs import resolve_env_references

        for text in ("${}", "${1BAD}", "plain-text"):
            assert not config_secrets.is_env_reference_text(text), text
            assert resolve_env_references(text, field_path="probe") == text

    def test_partially_substituted_text_is_literal_not_reference(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """掺了明文的串：F4 会替换其中的 ``${VAR}``，但它**不是纯引用** ⇒ ``kind`` 必须 literal。

        差别是有意义的：纯引用说明"值只在环境里"；混合串说明"磁盘上这段文字里确实有明文"。
        """
        from src.config.model_configs import resolve_env_references

        monkeypatch.setenv(self.PROBE_ENV_VAR, self.PROBE_VALUE)
        mixed = "prefix-${" + self.PROBE_ENV_VAR + "}"

        assert resolve_env_references(mixed, field_path="probe") == f"prefix-{self.PROBE_VALUE}"
        assert not config_secrets.is_env_reference_text(mixed)
        assert config_secrets.secret_kind(mixed) == "literal"

    def test_list_secret_is_reference_only_when_every_item_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """列表型秘密（``auth_token: list[str]``）：混着明文就归 literal，不装作"只是引用"。"""
        text = "${" + self.PROBE_ENV_VAR + "}"

        assert config_secrets.secret_kind([text, "  "]) == "reference"
        assert config_secrets.secret_kind([text, "sk-plain-in-the-file"]) == "literal"
        assert config_secrets.secret_kind([]) is None


# ── raw 系端点：可下线证据（本段**不删**，删不删等 lmq 拍板） ─────────


class TestRawEndpointRetirementEvidence:
    """``/config/bot/raw`` 的可下线证据。

    **这两条是"退役证据"性质的用例，不是"应当如此"的规格**：
    它们把"今天的 raw 端点长什么样"钉住——等它被删/被换形态那天，这两条会**失败**，
    逼着删它们的人同时把证据更新掉，而不是让证据烂在聊天记录里。

    实测（2026-10-16，worktree cfg-seam，夹具里是假密钥）：
    ``GET /api/webui/config/bot/raw`` ⇒ 200，返回体里 ``auth_token`` 与
    ``api_server_allowed_api_keys`` 的**真值都在**；同一份配置走新读接缝 ⇒ 一条真值都没有。
    """

    def test_raw_endpoint_returns_secret_values_in_plaintext(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """raw 端点是配置面上**最后一条明文密钥出站路径**（roadmap Problem 表第一行）。"""
        response = client.get("/api/webui/config/bot/raw")

        assert response.status_code == 200, response.text
        content = response.json()["content"]
        assert FAKE_BOT_TOKEN in content, "raw 端点仍然直出 auth_token 真值"
        assert FAKE_ALLOWED_KEY in content, "raw 端点仍然直出白名单密钥真值"

    def test_new_seam_serves_the_same_config_without_needing_the_raw_file(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """同一份配置走新读接缝：**非秘密字段一个不少地读得到**，秘密只有存在标记。

        ⇒ raw 端点剩下的独有价值只有"把密钥原文交给浏览器"这一件事；
        而编辑器要的那些字段（含注释以外的一切）路径读都能给。
        """
        entries = _entries_by_path(_read_paths(client, "bot"))

        assert entries["chat.max_context_size"]["value"] == 42
        assert entries["bot.nickname"]["value"] == "SeamBot"
        assert entries["maim_message.enable_api_server"]["value"] is True
        assert entries["inner.version"]["value"] == "0.9.0"
        assert entries["maim_message.auth_token"]["value"]["set"] is True
        assert FAKE_BOT_TOKEN not in str(entries)
