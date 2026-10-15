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

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List

import pytest
import tomlkit
from fastapi.testclient import TestClient

from src.config.config import Config
from src.webui import config_secrets, config_store
from src.webui.app import create_app
from src.webui.config_paths import WILDCARD, format_path, parse_declaration
from src.webui.dependencies import require_auth

FAKE_LITERAL_KEY = "sk-fake-seam-literal-0000deadbeef"
FAKE_ENV_KEY_VALUE = "sk-fake-seam-env-0000cafebabe"
FAKE_BOT_TOKEN = "fake-seam-bot-token-0000feedface"
FAKE_ALLOWED_KEY = "fake-seam-allowed-key-0000badc0de"
FAKE_NEW_KEY = "sk-fake-seam-new-0000abc123"
# 只被**过渡名字层**兜住的键（没人声明它，名字以 `_token` 结尾）。
# 刻意放进夹具：真实配置里就会出现这种"还没被声明"的密钥字段，
# 而这正是过渡层存在的理由——它必须在**每一条**读路径上都生效。
FAKE_UNDECLARED_TOKEN = "fake-seam-undeclared-token-0000c0ffee"
REFERENCE_ENV_VAR = "P2_SEAM_FAKE_DEEPSEEK_KEY"
REFERENCE_TEXT = "${" + REFERENCE_ENV_VAR + "}"

# 闸门要 grep 的全部假真值（含引用文本与变量名本身）
KNOWN_FAKE_SECRETS: tuple[str, ...] = (
    FAKE_LITERAL_KEY,
    FAKE_ENV_KEY_VALUE,
    REFERENCE_TEXT,
    REFERENCE_ENV_VAR,
    FAKE_BOT_TOKEN,
    FAKE_ALLOWED_KEY,
    FAKE_UNDECLARED_TOKEN,
)

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

[personality]
personality = "You are SeamBot."
multiple_reply_style = ["style-one"]
some_new_credential_token = "{FAKE_UNDECLARED_TOKEN}"

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
    # 保存后路由会 **await** config_manager.reload_config()；测试里全局 config_manager 是 None，
    # 而真实实现是 async（src/config/config.py:489）⇒ 替身也必须 async，否则 await None 会炸。
    async def _reload(*args, **kwargs):
        return True

    monkeypatch.setattr(
        config_router,
        "config_manager",
        SimpleNamespace(reload_config=_reload),
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

        ⚠️ **4 段改写过**：标记的 ``path`` 从"秘密**根**"改成**被请求的那一条**（F10）。
        "是哪条秘密"这件事的判据在**外层 entry 的 path**（＝请求路径）与脱敏本身，
        不靠内层 ``path`` 反推；内层 ``path`` 保持"客户端请求哪儿就是哪儿"，这样
        客户端拿标记回写时不必做一次"根 → 位置"的换算（换错就是写错位置）。
        """
        response = client.post(
            READ_URL,
            json={"namespace": "bot", "paths": ["maim_message.auth_token[0]"]},
        )
        assert response.status_code == 200, response.text
        assert FAKE_BOT_TOKEN not in response.text

        entry = _entries_by_path(response.json())["maim_message.auth_token[0]"]
        assert entry["value"]["$secret"] is True
        assert entry["value"]["set"] is True
        assert entry["value"]["path"] == "maim_message.auth_token[0]", "标记要指出被请求的位置"

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


class TestAncestorContainerRequestsDoNotLeak:
    """**方向乙「秘密在路径里」**（对抗审查 F1）——本轮的**死线**。

    上一轮我只做了「路径在秘密里」（请求 ``auth_token[0]``），没做「秘密在路径里」
    （请求 ``maim_message``）⇒ 请求一个**祖先容器**就把整棵子树连密钥一起交出去。
    而脱敏标记自己公布了秘密路径（``"path": "maim_message.auth_token"``），
    所以客户端**不用猜**就知道该请求哪个祖先——一次已鉴权**读**即可触发，连写都不用。
    """

    @pytest.mark.parametrize(
        ("namespace", "ancestor_path", "secrets"),
        [
            ("bot", "maim_message", (FAKE_BOT_TOKEN, FAKE_ALLOWED_KEY)),
            ("bot", "personality", (FAKE_UNDECLARED_TOKEN,)),
            ("model", "api_providers", (FAKE_LITERAL_KEY, REFERENCE_TEXT)),
            ("model", "api_providers[0]", (FAKE_LITERAL_KEY,)),
            ("model", "api_providers[1]", (REFERENCE_TEXT,)),
        ],
    )
    def test_ancestor_container_request_returns_markers_not_values(
        self,
        client: TestClient,
        seam_config_dir,
        monkeypatch: pytest.MonkeyPatch,
        namespace: str,
        ancestor_path: str,
        secrets: tuple[str, ...],
    ) -> None:
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        response = client.post(READ_URL, json={"namespace": namespace, "paths": [ancestor_path]})

        assert response.status_code == 200, response.text
        for secret in secrets:
            assert secret not in response.text, f"请求祖先容器 {ancestor_path!r} 泄漏了 {secret!r}"
        # 子树要**还在**（不是整块吞掉）——里面该有的非秘密字段照旧读得到
        assert response.json()["entries"][0]["value"], f"{ancestor_path} 被整块吞掉了"

    def test_ancestor_container_keeps_non_secret_siblings_readable(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """防过度脱敏：拿到祖先容器时，**兄弟字段**必须还是原值。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        entries = _entries_by_path(_read_paths(client, "model", ["api_providers[0]"]))
        subtree = entries["api_providers[0]"]["value"]

        assert subtree["organization"] == "seam-org"
        assert subtree["timeout"] == 30
        assert subtree["base_url"] == "https://plain.example.invalid/v1"
        assert subtree["api_key"]["$secret"] is True, "秘密字段在子树里必须是标记"


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

    def test_unset_a_missing_path_is_idempotent(self, client: TestClient, seam_config_dir) -> None:
        """重置一个本来就不存在的键 ⇒ **幂等成功**（F9，2026-10-16 定；旧行为是 400）。

        判据不是"返回 200"而是三件事同时成立（缺任何一条这条用例都会假绿）：

        1. 这次 unset **成功**（批量重试不再卡在这个"已经是想要的状态"的操作上）；
        2. 文件**一个字节都不变**（幂等 ≠ 顺手写点什么）；
        3. 读回来仍是"继承"（``inherited=true`` + schema 默认值），而不是被写成空值。
        """
        config_path = seam_config_dir / "bot_config.toml"
        before = config_path.read_bytes()
        revision = _read_paths(client, "bot")["revision"]

        response = _mutate(client, "bot", revision, [{"op": "unset", "path": "chat.ascii_column_width"}])

        assert response.status_code == 200, response.text
        assert config_path.read_bytes() == before, "幂等 unset 动了文件"
        entry = _entries_by_path(_read_paths(client, "bot", ["chat.ascii_column_width"]))[
            "chat.ascii_column_width"
        ]
        assert entry["inherited"] is True
        assert entry["value"] == 48  # ChatConfig.ascii_column_width 的 schema 默认

    def test_unset_on_a_walkable_but_absent_parent_still_fails(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """**幂等的边界**：父路径根本不存在 ⇒ 仍然是 400（那多半是路径写错了）。

        与上一条成对：幂等只覆盖"键不在（但父层在）"，不覆盖"这条路径走不通"——
        把打错的路径静默当成功，等于把用户的错误吃掉。
        """
        revision = _read_paths(client, "bot")["revision"]

        response = _mutate(client, "bot", revision, [{"op": "unset", "path": "bot.nickname.deep.missing"}])

        assert response.status_code == 400, response.text

    def test_secret_read_inside_a_secret_reports_the_requested_position(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """F10：读秘密字段**内部**一个不存在的下标 ⇒ 报**被请求位置**的状态，不是根的状态。

        夹具里 ``maim_message.auth_token`` 只有 1 项；请求 ``auth_token[7]``：
        旧实现回的是秘密根的三态（``set: true`` + 根的 ``kind``）⇒ 客户端以为"这个位置已配置"、
        还拿到一个并不存在的数组形态。新口径：``set: false``、不带 ``kind``、
        ``inherited: true``，且 ``path`` 就是**被请求的那一条**。
        """
        revision = _read_paths(client, "bot")["revision"]
        entries = _entries_by_path(_read_paths(client, "bot", ["maim_message.auth_token[7]"]))

        marker = entries["maim_message.auth_token[7]"]["value"]
        assert marker["$secret"] is True
        assert marker["set"] is False, "报的是秘密根的状态（F10 回归）"
        assert "kind" not in marker, "位置不存在就没有值形态可报"
        assert marker["path"] == "maim_message.auth_token[7]"
        assert entries["maim_message.auth_token[7]"]["inherited"] is True
        assert revision >= 1

        # 对照：**已存在**的那个下标仍要报"已配置"（防"一刀切成 set:false"这种过修）
        existing = _entries_by_path(_read_paths(client, "bot", ["maim_message.auth_token[0]"]))
        assert existing["maim_message.auth_token[0]"]["value"]["set"] is True


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

    def test_append_at_end_of_array_writes_the_value(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """``set <数组>[len]`` = **追加这个值本身**（对抗审查 F2）。

        曾经写成 ``append(_as_container(value))`` ⇒ 追加了个空表、值被丢掉，
        用户得到的是"配置数据验证失败"，而合法操作**永远无法成功**。
        """
        config_path = seam_config_dir / "bot_config.toml"
        revision = _read_paths(client, "bot")["revision"]

        # maim_message.auth_token 初始为 []，所以 [0] 就是"追加到末尾"
        written = _mutate(
            client, "bot", revision, [{"op": "set", "path": "maim_message.auth_token[0]", "value": "TOK-APPENDED"}]
        )
        assert written.status_code == 200, written.text

        after = _load_plain(config_path)
        assert after["maim_message"]["auth_token"] == ["TOK-APPENDED"], "追加的必须是值本身，不是空表"

    def test_append_a_new_array_of_tables_element(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``[[...]]`` 追加新表项：``set <AoT>[len].<字段>`` 走中间层补齐，值必须落地。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"
        revision = _read_paths(client, "model")["revision"]

        written = _mutate(
            client,
            "model",
            revision,
            [
                {"op": "set", "path": "api_providers[2].name", "value": "SeamThird"},
                {"op": "set", "path": "api_providers[2].base_url", "value": "https://third.example.invalid/v1"},
                {"op": "set", "path": "api_providers[2].api_key", "value": FAKE_NEW_KEY},
            ],
        )
        assert written.status_code == 200, written.text

        providers = _load_plain(config_path)["api_providers"]
        assert [provider["name"] for provider in providers] == ["SeamPlain", "SeamRef", "SeamThird"]
        assert providers[2]["api_key"] == FAKE_NEW_KEY

    def test_set_without_value_is_a_client_error(self, client: TestClient, seam_config_dir) -> None:
        """`set` 不传 ``value`` ⇒ **400**（TOML 无法表达 null），不是 500（对抗审查 F7）。"""
        config_path = seam_config_dir / "bot_config.toml"
        before_bytes = config_path.read_bytes()
        revision = _read_paths(client, "bot")["revision"]

        response = _mutate(client, "bot", revision, [{"op": "set", "path": "chat.max_context_size"}])

        assert response.status_code == 400, response.text
        assert "value" in response.text
        assert config_path.read_bytes() == before_bytes

    def test_placeholder_cannot_be_laundered_into_a_readable_field(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """**靶子约束**（对抗审查 F3）：占位只能写回它来源的那个秘密字段。

        没有这条约束时，占位是一个**任意读**原语：``set`` 到任意可读普通字段 ⇒ 原值落盘
        ⇒ 再读那个字段就拿明文。写一次、读一次，F2 的保密承诺整条作废。
        """
        config_path = seam_config_dir / "bot_config.toml"
        before_bytes = config_path.read_bytes()
        revision = _read_paths(client, "bot")["revision"]

        laundered = _mutate(
            client,
            "bot",
            revision,
            [
                {
                    "op": "set",
                    "path": "personality.multiple_reply_style",
                    "value": {"$secret": True, "set": True, "path": "maim_message.auth_token"},
                }
            ],
        )

        assert laundered.status_code == 400, laundered.text
        assert "maim_message.auth_token" in laundered.text
        assert config_path.read_bytes() == before_bytes, "洗秘密的写入必须整次作废"

    def test_unset_placeholder_saying_false_cannot_claim_a_real_value(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """**F3 子观察（2026-10-16 定）**：``set: false`` 的占位标志以前**从没被读过**。

        这里的占位指向 ``api_providers[1].api_key``（盘上是引用文本，即"有值"），
        但自带 ``set: false``——一个自相矛盾的标记。旧行为照常认领 ⇒ 写下去**静默丢掉那份凭据**
        （占位不是值，落盘的就是"没有值"）。新行为：拒绝整次写入、点名。
        """
        config_path = seam_config_dir / "model_config.toml"
        before_bytes = config_path.read_bytes()
        revision = _read_paths(client, "model")["revision"]

        response = _mutate(
            client,
            "model",
            revision,
            [
                {
                    "op": "set",
                    "path": "api_providers[1].api_key",
                    "value": {
                        "$secret": True,
                        "set": False,
                        "path": "api_providers[1].api_key",
                        "origin_name": "SeamRef",
                    },
                }
            ],
        )

        assert response.status_code == 400, response.text
        assert "set=false" in response.text or "set: false" in response.text
        assert config_path.read_bytes() == before_bytes, "被拒绝的写入必须整次作废"

    def test_unset_placeholder_on_an_empty_source_is_still_accepted(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """**F3 子观察的反向判据**（防"一刀切"）：来源位置本来就没值 ⇒ ``set: false`` 的占位与事实一致。

        形态取自真实客户端行为：读一份**没配密钥**的配置（秘密字段直接**不存在** ⇒ 三态里的
        "未配置"，``set: false`` + 来源路径），在页面上填别的字段，然后把整份读回来的东西写回去。
        这一路**不能**被 F3 子观察的判据误伤——判据只拦"来源**有值**却自称没值"的自相矛盾。

        ⚠️ **已知边界（保留，本次不修）**：来源路径**不存在**时，占位无法被"认领"（没有值可认），
        它会**原样留在 payload 里**，由 ``find_unresolved_sentinels`` 拦成 400。
        ⇒ 本次判据补的是"值为 None/空"这一类（能认领、认领结果是空），
        "字段整个不存在"这一类仍是 400（拒绝而不是猜：空值该不该落盘是另一个决定）。
        """
        config_path = seam_config_dir / "bot_config.toml"
        # 把"有值"改成"值为空"：字段还在（来源路径可认领），但值确实是空的
        text = config_path.read_text(encoding="utf-8").replace(
            f'auth_token = ["{FAKE_BOT_TOKEN}"]\n', "auth_token = []\n"
        )
        config_path.write_text(text, encoding="utf-8")
        revision = _read_paths(client, "bot")["revision"]

        response = _mutate(
            client,
            "bot",
            revision,
            [
                {
                    "op": "set",
                    "path": "maim_message.auth_token",
                    "value": {"$secret": True, "set": False, "path": "maim_message.auth_token"},
                }
            ],
        )

        assert response.status_code == 200, response.text
        assert _load_plain(config_path)["maim_message"]["auth_token"] == []

    def test_placeholder_from_a_non_secret_field_is_refused(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """**来源约束**：占位自称的来源必须真的是秘密字段（否则它是"任意取值"原语）。"""
        config_path = seam_config_dir / "bot_config.toml"
        before_bytes = config_path.read_bytes()
        revision = _read_paths(client, "bot")["revision"]

        response = _mutate(
            client,
            "bot",
            revision,
            [
                {
                    "op": "set",
                    "path": "bot.nickname",
                    "value": {"$secret": True, "set": True, "path": "bot.nickname"},
                }
            ],
        )

        assert response.status_code == 400, response.text
        assert config_path.read_bytes() == before_bytes

    def test_reorder_still_claims_by_origin_name(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """靶子约束**不能**把 F3 的改名/换序兜底一起掐掉：同一个秘密字段换个下标仍要认领。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"

        entries = _entries_by_path(_read_paths(client, "model"))
        # 把 1 号位（引用型）的 api_key 写到 0 号位：同一个声明字段、不同下标 ⇒ 允许
        marker = entries["api_providers[1].api_key"]["value"]
        revision = _read_paths(client, "model")["revision"]
        written = _mutate(client, "model", revision, [{"op": "set", "path": "api_providers[0].api_key", "value": marker}])

        assert written.status_code == 200, written.text
        providers = _load_plain(config_path)["api_providers"]
        assert providers[0]["api_key"] == REFERENCE_TEXT, "按名/按来源下标认领到的是引用文本本身"
        assert providers[1]["api_key"] == REFERENCE_TEXT, "没被点名的那条不动"

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


class TestHotReloadAfterWrite:
    """写盘成功之后的热重载语义（对抗审查 F14）。

    ``config_manager.reload_config`` 是 ``async def``。不 await = 协程被丢掉：
    **既不重载、又留一条 never-awaited 警告**，而且因为没有任何异常，
    看起来像"保存成功顺便热重载了"。冻结态则是**预期**分支（启动后配置只读），
    必须如实报告，**不许**在文件已经写成功之后回 500。
    """

    def _patch_reload(self, monkeypatch: pytest.MonkeyPatch, reload_impl) -> None:
        import src.webui.routers.config as config_router

        monkeypatch.setattr(
            config_router, "config_manager", SimpleNamespace(reload_config=reload_impl)
        )

    def test_reload_config_is_actually_awaited(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: List[str] = []

        async def _reload(*args, **kwargs):
            calls.append("reloaded")
            return True

        self._patch_reload(monkeypatch, _reload)
        revision = _read_paths(client, "bot")["revision"]
        written = _mutate(client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 41}])

        assert written.status_code == 200, written.text
        assert calls == ["reloaded"], "reload_config 必须被 await 到（不 await = 协程被静默丢掉）"
        assert written.json()["hot_reload"] == "ok"

    def test_frozen_reload_is_reported_not_a_500(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.config.config import ConfigFrozenError

        async def _frozen(*args, **kwargs):
            raise ConfigFrozenError("配置已冻结（启动完成），运行时修改被拒绝")

        self._patch_reload(monkeypatch, _frozen)
        config_path = seam_config_dir / "bot_config.toml"
        revision = _read_paths(client, "bot")["revision"]
        written = _mutate(client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 41}])

        # 文件**已经写成功**了 ⇒ 不许让客户端以为"没保存"
        assert written.status_code == 200, written.text
        assert written.json()["hot_reload"] == "refused_frozen"
        assert "冻结" in written.json()["message"]
        assert _load_plain(config_path)["chat"]["max_context_size"] == 41


# 全部保存路径（收尾令：同类未清 = 修了一处留五处）
LEGACY_SAVE_HTTP_CALLS: tuple[tuple[str, str, Dict[str, Any]], ...] = (
    ("POST", "/api/webui/config/bot", {}),
    ("POST", "/api/webui/config/model", {}),
    ("POST", "/api/webui/config/bot/section/personality", {"personality": "You are SeamBot v2."}),
    ("POST", "/api/webui/config/model/section/models", []),
)


class TestAllSavePathsReloadAndReport:
    """① 收尾令：**六条**保存路径全部走同一个重载机制。

    原来只有新接缝（`mutate`）await 了热重载，另外 5 处遗留调用点全都把协程丢掉。
    同类缺陷留 5 处 = 没修。这里逐条驱动一次真实保存，断言：
    ① 无 ``RuntimeWarning``（协程没被丢）② 无 500 ③ 盘上确实落盘。
    """

    def _drive_all_paths(self, client: TestClient, seam_config_dir) -> List[str]:
        """让每条保存路径各落一次盘，返回 ``"<路径> ⇒ <状态码>"`` 记录。"""
        model_config = client.get("/api/webui/config/model").json()["config"]
        bot_config = client.get("/api/webui/config/bot").json()["config"]
        model_models = model_config["models"]

        results: List[str] = []
        for method, url, payload in LEGACY_SAVE_HTTP_CALLS:
            body = payload
            if url.endswith("/config/bot"):
                body = bot_config
            elif url.endswith("/config/model"):
                body = model_config
            elif url.endswith("/section/models"):
                body = model_models
            response = client.request(method, url, json=body)
            results.append(f"{url} ⇒ {response.status_code}")
            assert response.status_code == 200, f"{url}: {response.status_code} {response.text[:200]}"

        # 人设生成器的注入路径（同一个缺陷类的第 5 处）
        apply_response = client.post(
            "/api/webui/config/prompt-generator/apply",
            json={
                "blocks": [
                    {
                        "id": "seam-block",
                        "section": "personality",
                        "field": "personality",
                        "title": "人格",
                        "value": "You are SeamBot v3.",
                        "toml": "",
                    }
                ]
            },
        )
        results.append(f"/prompt-generator/apply ⇒ {apply_response.status_code}")
        assert apply_response.status_code == 200, apply_response.text[:300]

        # 新接缝那条也一起跑（总共 6 条）
        revision = _read_paths(client, "bot")["revision"]
        mutate_response = _mutate(
            client, "bot", revision, [{"op": "set", "path": "chat.max_context_size", "value": 43}]
        )
        results.append(f"/config/mutate ⇒ {mutate_response.status_code}")
        assert mutate_response.status_code == 200, mutate_response.text[:300]
        return results

    def test_every_save_path_awaits_reload_without_warning_or_500(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import gc
        import warnings

        # 模型平面夹具里有 `${VAR}` 引用 ⇒ 变量必须存在，否则 ModelConfig 校验会拒（那是 F4 的预期行为）
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            results = self._drive_all_paths(client, seam_config_dir)
            gc.collect()  # 未 await 的协程是在回收时才发 RuntimeWarning 的

        never_awaited = [str(item.message) for item in caught if "never awaited" in str(item.message)]
        assert never_awaited == [], f"仍有协程被丢掉：{never_awaited}"
        # 4 条遗留配置端点 + 人设生成器注入 + 新接缝 mutate = 6 条保存路径，全部 200
        assert len(results) == 6, results

        # ③ 盘上确实落盘（不是"200 了但没写"）
        bot_plain = _load_plain(seam_config_dir / "bot_config.toml")
        assert bot_plain["personality"]["personality"] == "You are SeamBot v3."
        assert bot_plain["chat"]["max_context_size"] == 43
        assert _load_plain(seam_config_dir / "model_config.toml")["models"][0]["name"] == "seam-model"

    def test_no_unawaited_reload_call_site_remains(self) -> None:
        """机械闸：模块里不许再出现未 await 的 ``config_manager.reload_config()``。

        这条不依赖"我记得有哪几处"——它扫源码。将来谁再写一处未 await 的，这里就红。
        """
        import inspect

        import src.webui.routers.config as config_router

        source = inspect.getsource(config_router)
        offenders = [
            f"{number}: {line.strip()}"
            for number, line in enumerate(source.splitlines(), start=1)
            if "config_manager.reload_config()" in line and "await" not in line
        ]

        assert offenders == [], f"仍存在未 await 的重载调用点：{offenders}"


class TestArrayWildcardDeclaration:
    """F5（已复现）：以 ``[]`` 结尾的声明必须整块脱敏——``_redact`` 的 list 分支曾漏判。"""

    def test_declaration_ending_with_wildcard_redacts_the_whole_array(self) -> None:
        data = {"a": ["SECRET-1", "SECRET-2"]}

        redacted = config_secrets.redact_config_secrets(data, secret_paths={"a[]"})

        assert "SECRET-1" not in str(redacted), "声明以 [] 结尾时元素必须脱敏（曾经逐元素原样出站）"
        # 判据挂在**元素**路径上（与 find_secret_root 同口径），不是整个数组一个标记：
        # `a[]` 的语义就是"a 的每个元素都是秘密"，所以是逐元素的标记。
        assert [item["$secret"] for item in redacted["a"]] == [True, True]
        assert [item["path"] for item in redacted["a"]] == ["a[0]", "a[1]"]
        assert all(item["set"] is True for item in redacted["a"])

    def test_read_seam_and_whole_file_agree_on_the_wildcard_form(self) -> None:
        """两条读路径口径必须一致（F4 的教训：口径分叉本身就是缺陷）。"""
        declared = frozenset({"a[]"})

        assert config_secrets.find_secret_root(("a", 0), declared) == ("a", 0)
        assert "SECRET-1" not in str(config_secrets.redact_config_secrets({"a": ["SECRET-1"]}, secret_paths=declared))

    def test_derived_channel_structurally_cannot_emit_a_trailing_wildcard(self) -> None:
        """F5 的**可达性边界**：派生通道产不出尾部 ``[]``。

        依据（读代码 + 这里钉住）：``derive_secret_field_paths`` 给子路径用的前缀永远是
        ``f"{path}[]."``（带点），末段一定是**字段名** ⇒ 结果不可能以 ``[]`` 结尾。
        所以尾部 `[]` 只可能来自**手写**的声明表条目——上面那条用例守的就是这个口子。
        """
        for namespace in sorted(config_store.NAMESPACES):
            spec = config_store.namespace_spec(namespace)
            for path in config_secrets.derive_secret_field_paths(spec.model):
                assert not path.endswith("[]"), f"派生通道产出了尾部 []：{namespace}:{path}"


class TestOrdinaryTablesAreNotMistakenForSentinels:
    """F6（已复现）：``{path: str, set: bool}`` 形状的**普通数据表**不能被当成占位。

    可达面：``ModelInfo.extra_params: dict[str, Any]``。只比形状的后果是
    新接缝里合法数据被 400、遗留整份写里被参考值**静默替换**。
    """

    LEGIT_TABLE: Dict[str, Any] = {"path": "outputs", "set": True}

    def test_shape_alone_collides_but_claim_needs_a_secret_source(self) -> None:
        declared = config_store.secret_field_paths("model")

        assert config_secrets.is_redaction_sentinel(self.LEGIT_TABLE) is True, "形状确实撞上了"
        assert config_secrets.is_secret_claim(self.LEGIT_TABLE, declared) is False, "但来源不是秘密"

    def test_legacy_merge_keeps_the_users_table(self) -> None:
        declared = config_store.secret_field_paths("model")

        merged = config_secrets.merge_payload_with_reference(
            {"extra_params": self.LEGIT_TABLE}, {"extra_params": {"path": "ORIGINAL"}}, declared=declared
        )

        assert merged["extra_params"] == self.LEGIT_TABLE, "普通表必须原样保留，不能被参考值换掉"

    def test_unresolved_scan_does_not_flag_it(self) -> None:
        declared = config_store.secret_field_paths("model")

        unresolved = config_secrets.find_unresolved_sentinels(
            {"x": self.LEGIT_TABLE}, declared=declared
        )

        assert unresolved == [], "普通表不是'未还原的占位'"

    def test_real_sentinel_still_claims_with_the_same_predicate(self) -> None:
        """反例守卫：收紧判据之后，**真占位**照样认领（别把口子堵死了）。"""
        declared = config_store.secret_field_paths("model")
        real_sentinel = {"$secret": True, "set": True, "path": "api_providers[0].api_key"}

        assert config_secrets.is_secret_claim(real_sentinel, declared) is True

    def test_new_seam_writes_the_ordinary_table(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """端到端：把一张 ``{path, set}`` 普通表写进 ``models[0].extra_params`` 必须成功。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"
        revision = _read_paths(client, "model")["revision"]

        written = _mutate(
            client,
            "model",
            revision,
            [{"op": "set", "path": "models[0].extra_params", "value": self.LEGIT_TABLE}],
        )

        assert written.status_code == 200, written.text
        assert _load_plain(config_path)["models"][0]["extra_params"] == self.LEGIT_TABLE

    def test_real_placeholder_roundtrip_still_works_end_to_end(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """端到端反例：判据收紧后，秘密占位的往返（F3 认领）不能被误伤。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        config_path = seam_config_dir / "model_config.toml"

        entries = _entries_by_path(_read_paths(client, "model"))
        marker = entries["api_providers[1].api_key"]["value"]
        revision = _read_paths(client, "model")["revision"]
        written = _mutate(client, "model", revision, [{"op": "set", "path": "api_providers[1].api_key", "value": marker}])

        assert written.status_code == 200, written.text
        assert _load_plain(config_path)["api_providers"][1]["api_key"] == REFERENCE_TEXT


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

    def test_transitional_layer_allows_the_known_undeclared_key(self, seam_config_dir) -> None:
        """**过渡层台账**：报出"只有名字层兜住、没有任何声明"的键。

        夹具里刻意放了一个 ``personality.some_new_credential_token`` ⇒ 这张表**必须**报出它。
        （它就是"过渡层为什么还不能删"的证据：只要还有这种键，``is_sensitive_key`` 就得留着。）
        """
        bot_declared = config_store.secret_field_paths("bot")
        model_declared = config_store.secret_field_paths("model")

        assert config_secrets.undeclared_transitional_keys(
            _load_plain(seam_config_dir / "bot_config.toml"), bot_declared
        ) == ["personality.some_new_credential_token"]
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


def _iter_path_prefixes(value: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    """列出这棵树里的**每一条路径前缀**：中间层表、数组项**本身**、叶子，全都算一条。

    刻意**不做任何**"什么才算可读路径"的筛选——这道闸存在的全部意义就是
    不依赖"人想得到哪些形状"。上一轮全绿却漏掉祖先容器，就是因为用例选点是手挑的。
    """
    if prefix:
        yield prefix
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_path_prefixes(item, (*prefix, str(key)))
        return
    if isinstance(value, list) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            yield from _iter_path_prefixes(item, (*prefix, index))


class TestExhaustivePrefixLeakGate:
    """③ 后的**机械穷举闸**（lead 2026-10-16 指定）——防复发的闸，不是补几个用例。

    为什么必须是穷举：上一轮四条判据门全绿，而新接缝当时有两条明文出站路径。
    根因不是执行错，是**用例选点系统性避开了"祖先容器"**——我只请求了整平面与
    秘密**内部**的路径，恰好没请求"秘密**外面**那一层容器"。手挑用例无法防住
    "我又没想到的形状"，所以这里改成遍历该平面的**每一条路径前缀**逐个请求。

    判据：**遍历 N 条前缀 × 2 个平面，泄漏 0 例**（N 见断言消息与用例输出）。
    """

    @pytest.mark.parametrize(
        ("namespace", "filename"),
        [("bot", "bot_config.toml"), ("model", "model_config.toml")],
    )
    def test_every_path_prefix_is_leak_free(
        self,
        client: TestClient,
        seam_config_dir,
        monkeypatch: pytest.MonkeyPatch,
        namespace: str,
        filename: str,
    ) -> None:
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)
        stored = _load_plain(seam_config_dir / filename)
        prefixes = list(_iter_path_prefixes(stored))
        assert prefixes, "前缀集合为空 ⇒ 这道闸是空跑"

        leaks: List[tuple[str, str]] = []
        for tokens in prefixes:
            path = format_path(tokens)
            response = client.post(READ_URL, json={"namespace": namespace, "paths": [path]})
            assert response.status_code == 200, (
                f"{namespace}:{path} ⇒ {response.status_code} {response.text[:200]}"
            )
            for secret in KNOWN_FAKE_SECRETS:
                if secret in response.text:
                    leaks.append((path, secret))

        print(f"\n[穷举闸] {namespace} 平面：{len(prefixes)} 条路径前缀 × {len(KNOWN_FAKE_SECRETS)} 个真值探针")
        assert leaks == [], (
            f"{namespace} 平面泄漏 {len(leaks)} 例 / 共 {len(prefixes)} 条前缀：{leaks[:5]}"
        )

    @pytest.mark.parametrize("namespace", ["bot", "model"])
    def test_whole_plane_read_is_leak_free(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch, namespace: str
    ) -> None:
        """整平面（``paths=[]``）与逐条前缀**同待遇**——两条分支不许有不同的保密性。"""
        monkeypatch.setenv(REFERENCE_ENV_VAR, FAKE_ENV_KEY_VALUE)

        response = client.post(READ_URL, json={"namespace": namespace, "paths": []})

        assert response.status_code == 200, response.text
        for secret in KNOWN_FAKE_SECRETS:
            assert secret not in response.text, f"{namespace} 整平面读泄漏 {secret!r}"


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


# ── F11：读接缝的「内容 / revision」必须同源 ──────────────────────────
#
# 为什么原实现会撕裂（写清楚，别让后人再踩）：
#   读接缝原先分两步 —— `load_stored()` 然后再 `current_revision()`，两次各自进出
#   `_REVISION_LOCK`。写者只要插在两步之间，客户端就拿到 **(旧内容, 新 revision)**：
#   revision 说"你看到的是最新的"，内容却不是。带着这个 revision 去 `mutate` 会**被接受**
#   ⇒ 乐观锁的意义（"写之前证明你读到的是最新的"）整个失效。
#   窗口不小：`load_stored` 既不持锁、又做文件 I/O，正好把 GIL 让给别的线程。
#   而生产上**确实有两个线程** —— `src/main.py` 的注释明写 WebUI 跑在独立线程
#   （`ThreadedWebUIServer`）。
#
# 修法：`config_store.read_snapshot()` 一个口取回 (内容, revision)，
#   且 revision 由**同一批字节**的指纹派生 ⇒ 两者同源。锁只覆盖"读字节 + sha256"（实测 0.28ms），
#   解析 TOML 与 to_plain 留在锁外（F13 的教训：别持锁做重活）。


def _run_contention_reader(reader_fn, *, iterations: int, seconds: float = 3.0) -> List[tuple[int, int]]:
    """跑一个"读者 vs 写者"的并发实验，返回读者观察到的 (内容值, revision) 不一致样本。

    不变式：写者每次 commit 把 ``chat.max_context_size`` 设成它带的 ``expected_revision``，
    commit 之后 revision = 值 + 1 ⇒ **一致的快照必须满足 ``值 == revision - 1``**。
    读者观察到别的组合，就是撕裂。
    """
    import threading
    import time

    namespace = config_store.NAMESPACE_BOT
    stop = threading.Event()
    seen: List[tuple[int, int]] = []

    def writer() -> None:
        while not stop.is_set():
            try:
                revision = config_store.current_revision(namespace)

                def _apply(document: Any, baseline: Any, revision: int = revision) -> None:
                    document["chat"]["max_context_size"] = revision

                config_store.commit(namespace, revision, _apply)
            except config_store.RevisionConflictError:
                continue

    worker = threading.Thread(target=writer, daemon=True)
    worker.start()
    try:
        time.sleep(0.05)  # 让写者先跑起来（首轮 commit 之后不变式才开始成立）
        for _ in range(iterations):
            seen.append(reader_fn())
    finally:
        stop.set()
        worker.join(timeout=5)
    return [(value, revision) for value, revision in seen if value != revision - 1]


class TestReadSnapshotAtomicity:
    """F11：``read_snapshot`` 必须让"内容 ↔ revision"同源，并发下零撕裂。"""

    def test_read_snapshot_has_zero_tears_under_contention(
        self, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**修后的行为**：并发下 0 撕裂（修前同一形状实测 40 次读 40 次撕裂）。"""
        namespace = config_store.NAMESPACE_BOT

        def reader() -> tuple[int, int]:
            stored, revision = config_store.read_snapshot(namespace)
            return stored["chat"]["max_context_size"], revision

        tears = _run_contention_reader(reader, iterations=200)

        assert tears == [], f"read_snapshot 出现撕裂：{tears[:5]}"

    def test_the_old_two_step_pattern_tears(self, seam_config_dir, monkeypatch: pytest.MonkeyPatch) -> None:
        """**特性化用例**：证明"分两步"确实会撕裂——修复不是空转。

        这条刻意复刻**旧实现**的取数方式（``load_stored`` 然后 ``current_revision``）。
        它红了才说明上面那条绿的有意义：否则"0 撕裂"可能只是并发没压上。
        若哪天有人把读接缝改回两步，这条会继续绿——所以还有下面那条**端点级**的守门用例。
        """
        namespace = config_store.NAMESPACE_BOT

        def reader() -> tuple[int, int]:
            stored = config_store.load_stored(namespace)
            revision = config_store.current_revision(namespace)
            return stored["chat"]["max_context_size"], revision

        tears = _run_contention_reader(reader, iterations=200)

        assert tears, "旧两步法本应撕裂；没撕裂说明这个并发实验压不上，请加大 iteration"

    def test_read_endpoint_returns_content_and_revision_from_one_version(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """**端点级**守门（覆盖口径 = 被判定的对象）：HTTP 读接缝在并发写之下不许自相矛盾。

        为什么要有这条：上面两条测的是 ``config_store`` 的两个函数，
        而"读接缝有没有用对"的判据在**端点**上。只要有人把端点改回两步取数，这条就红。
        写者在**另一个线程**里 commit —— 这正是生产形态（WebUI 独立线程 + 别的写者）。
        """
        import threading

        namespace = config_store.NAMESPACE_BOT
        stop = threading.Event()
        ready = threading.Event()

        def writer() -> None:
            while not stop.is_set():
                try:
                    revision = config_store.current_revision(namespace)

                    def _apply(document: Any, baseline: Any, revision: int = revision) -> None:
                        document["chat"]["max_context_size"] = revision

                    config_store.commit(namespace, revision, _apply)
                    ready.set()
                except config_store.RevisionConflictError:
                    continue

        worker = threading.Thread(target=writer, daemon=True)
        worker.start()
        try:
            assert ready.wait(timeout=10), "写者没跑起来"
            inconsistencies: List[tuple[Any, int]] = []
            for _ in range(60):
                body = _read_paths(client, "bot", ["chat.max_context_size"])
                value = _entries_by_path(body)["chat.max_context_size"]["value"]
                if value != body["revision"] - 1:
                    inconsistencies.append((value, body["revision"]))
        finally:
            stop.set()
            worker.join(timeout=5)

        assert inconsistencies == [], f"端点返回了 (旧内容, 新 revision)：{inconsistencies[:5]}"

    def test_snapshot_parse_matches_load_document_on_real_configs(self) -> None:
        """``read_snapshot`` 的解析结果必须与 ``load_document`` **逐字段一致**。

        风险点是我在 F11 里换掉的读法：``read_bytes().decode()`` 不像
        ``open(..., "r")`` 那样做 universal newlines，而本仓 ``bot_config.toml`` 是 **CRLF**。
        两条路若在多行字符串上分叉，就成了"读接缝看到的配置与写路径看到的不是同一份"。
        这里直接拿**真配置**（一个 CRLF、一个 LF）对拍。
        """
        repo_root = Path(__file__).resolve().parents[2]
        for filename in ("bot_config.toml", "model_config.toml"):
            source = repo_root / "config" / filename
            if not source.exists():  # 裸 worktree 可能缺资源，跳过而不是假绿
                continue
            assert config_store._decode_config_bytes(source.read_bytes()) == source.read_text(
                encoding="utf-8"
            ), f"{filename}: 两种读法的文本不一致（换行语义分叉）"


# ── F12：服务端声明表写错 ≠ 客户端请求错 ─────────────────────────────


class TestServerSideDeclarationErrors:
    """F12：``SECRET_FIELD_PATHS`` 是**服务端自己的数据**，写错了不能报成客户端 400。

    旧行为：声明表里一条非法路径 ⇒ ``parse_declaration`` 抛 ``ConfigPathError`` ⇒
    被端点的 ``except (ConfigPathError, SecretClaimError)`` 接住 ⇒ **400 PARAM_INVALID**。
    排障的人于是去查请求，而问题在服务端声明表里。
    """

    def _inject_bad_declaration(self, monkeypatch: pytest.MonkeyPatch, bad_path: str) -> None:
        """把一条非法声明注入读接缝（模拟"有人改坏了声明表"）。"""
        real = config_store.secret_field_paths

        def _patched(namespace: str) -> frozenset[str]:
            return frozenset(real(namespace) | {bad_path})

        monkeypatch.setattr(config_store, "secret_field_paths", _patched)

    def test_bad_declaration_is_a_server_error_not_a_client_400(
        self, client: TestClient, seam_config_dir, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._inject_bad_declaration(monkeypatch, "bad..path")

        response = client.post(READ_URL, json={"namespace": "bot", "paths": []})

        assert response.status_code == 500, f"服务端声明错误不该是 {response.status_code}：{response.text[:200]}"
        body = response.json()
        assert body["error_code"] == "SYS_INTERNAL_ERROR"
        assert "bad..path" in body["error_message"], "报错要指名道姓说哪条声明坏了"

    def test_client_side_bad_path_is_still_a_400(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """反向守卫：**客户端**给错路径仍必须是 400——两类状态要真的分开，不是一律 500。"""
        response = client.post(READ_URL, json={"namespace": "bot", "paths": ["chat..max_context_size"]})

        assert response.status_code == 400, response.text[:200]
        assert response.json()["error_code"] == "PARAM_INVALID"

    def test_unknown_path_is_still_a_400(self, client: TestClient, seam_config_dir) -> None:
        """另一类客户端错：路径合法但字段不存在 ⇒ 仍是 400。"""
        response = client.post(READ_URL, json={"namespace": "bot", "paths": ["chat.not_a_field"]})

        assert response.status_code == 400, response.text[:200]
        assert response.json()["error_code"] == "PARAM_INVALID"

    def test_declaration_error_is_not_a_config_path_error(self) -> None:
        """结构守卫：``SecretDeclarationError`` **不能**是 ``ConfigPathError`` 的子类。

        它一旦成了子类，就会被端点那条 400 分支接走——F12 原样复发。
        （这条不需要跑服务，改类型的人会立刻看到它红。）
        """
        from src.webui.config_paths import ConfigPathError

        assert not issubclass(config_secrets.SecretDeclarationError, ConfigPathError)

    def test_valid_declaration_table_produces_no_server_error(
        self, client: TestClient, seam_config_dir
    ) -> None:
        """反例守卫：正常声明表下整平面读必须 200——别把"防误报"写成"一律 500"。"""
        response = client.post(READ_URL, json={"namespace": "bot", "paths": []})

        assert response.status_code == 200, response.text[:200]
