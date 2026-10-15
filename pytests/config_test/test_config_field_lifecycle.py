"""4 段本体 · 字段生命周期（``deprecate → replace → remove``）的回归测试。

守的是**静默丢弃**这个病灶：`ConfigBase.from_dict` 对"模型里没有的键"是 ``pop`` 掉
（只在升级改写时打一行 INFO）⇒ 用户改一个**已被移除**的字段时，程序不报错也不生效，
改动被悄悄吃掉。本模块把名字消失变成显式的事：弃用出声、移除拒绝。

四组判据：

1. **deprecate 只出声**（``TestDeprecate``）：文件里有已声明弃用的字段 ⇒ 不抛异常、
   原值照常加载、日志里有点名；没有这个字段时不刷警告（**反向判据**，防"天天响"）。
2. **remove 显式拒绝**（``TestRemoveRefuses``）：类型化异常 + 消息带字段路径/替代者/
   文件名；**盘上字节不动**（拒绝发生在任何写入之前）。
3. **遍历按 schema 走、且不下钻 dict 根**（``TestTraversalBoundary``）：
   数组元素与嵌套子表都能命中；``dict[str, X]`` 型字段（键由数据决定）不误报。
4. **声明表本身**（``TestDeclarationTable``）：入表纪律的机械判据——每条声明的路径
   必须真的在 schema 里存在（防"声明了一个拼错的字段名"这种静默失效）。

⚠️ **别用真表跑"移除"用例**：今天表里的 6 条都是 ``DEPRECATED``（字段还在，能被无害地
弃用）。``REMOVED`` 的形态用 ``monkeypatch`` 注入合成声明来造——这也是"注入式判据"
的既有先例（版本链的"迁移器未登记"那条就是这么测的）。
"""

import logging  # noqa: TID251 — 仅取 `logging.WARNING` 这个整数常量配合 pytest 的 caplog；
# 用 `src.common.logger.get_logger()` 取不到它（那是项目自己的 logger 封装），而过滤器层级
# 必须与生产代码一致，否则本用例会因为"记录被过滤掉"而假绿。
from pathlib import Path

import pytest
import tomlkit

from src.config.config import (
    CONFIG_VERSION,
    MODEL_CONFIG_VERSION,
    Config,
    ModelConfig,
    generate_new_config_file,
    load_config_from_file,
)
from src.config import config_lifecycle
from src.config.config_lifecycle import (
    ConfigFieldRefusedError,
    FieldLifecycle,
    FieldLifecycleState,
    check_field_lifecycle,
    collect_generated_paths,
    declarations_for,
    lifecycle_of,
    removed_field_paths,
)

FAKE_FILE = "probe/bot_config.toml"

# 表里真实存在的一条（`fuzzy_modify_*` 组；证据见 `config_lifecycle.py` 声明表上方注释）
REAL_DEPRECATED_PATH = "a_memorix.integration.fuzzy_modify_enabled"


# ── 1 · deprecate 只出声 ──────────────────────────────────────────────


class TestDeprecate:
    """弃用期：**不报错**、原值照常生效、出声点名。"""

    def test_real_declaration_is_reachable_in_schema(self) -> None:
        """前置：表里那 6 条声明的宿主字段确实还在 schema 里（否则下面的用例测不到东西）。"""
        declaration = lifecycle_of(Config, REAL_DEPRECATED_PATH)

        assert declaration is not None
        assert declaration.state is FieldLifecycleState.DEPRECATED
        # 逐层验证路径真的走得通（拼错一个字母就会变成"永不命中"的静默失效）
        node = Config
        for part in REAL_DEPRECATED_PATH.split(".")[:-1]:
            node = node.model_fields[part].annotation
        assert REAL_DEPRECATED_PATH.split(".")[-1] in node.model_fields

    def test_present_deprecated_field_warns_but_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        data = {"a_memorix": {"integration": {REAL_DEPRECATED_PATH.split(".")[-1]: True}}}

        with caplog.at_level(logging.WARNING, logger="config.config_lifecycle"):
            hits = check_field_lifecycle(Config, data, file_name=FAKE_FILE)

        assert hits == [REAL_DEPRECATED_PATH]
        assert REAL_DEPRECATED_PATH in caplog.text
        assert FAKE_FILE in caplog.text

    def test_generated_default_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        """**"只对用户显式保留的选择出声"**：程序生成的默认值形态 ⇒ 不出声。

        这是实测出来的必要（不是设计洁癖）：`generate_new_config_file` 落盘的默认
        `bot_config.toml` **自己就带着那 6 个弃用字段** ⇒ 没有抑制集时，用户什么都没改也会在
        每次启动看到 6 条警告，"提示"直接退化成"背景噪声"。

        判据：同一份数据，`generated_paths` 给全（＝这是我们的默认值）⇒ `caplog` 里
        **一条 WARNING 都没有**，但返回值照旧列出命中的路径（调用方仍知道"这里有弃用字段"）。
        """
        data = {
            "a_memorix": {
                "integration": {
                    "fuzzy_modify_enabled": True,
                    "fuzzy_modify_max_targets": 5,
                }
            }
        }
        generated = collect_generated_paths(Config, data)
        assert generated == frozenset(
            {
                "a_memorix.integration.fuzzy_modify_enabled",
                "a_memorix.integration.fuzzy_modify_max_targets",
            }
        )

        with caplog.at_level(logging.WARNING, logger="config.config_lifecycle"):
            hits = check_field_lifecycle(Config, data, file_name=FAKE_FILE, generated_paths=generated)

        assert hits == [
            "a_memorix.integration.fuzzy_modify_enabled",
            "a_memorix.integration.fuzzy_modify_max_targets",
        ]
        assert caplog.text == "", "程序自己写的默认值也出声了（噪声）"

    def test_user_kept_key_still_warns_when_absent_from_generated(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """反向判据：键**不在**程序默认值里（＝用户自己留的）⇒ 照常出声。

        与上一条成对——只有"默认值静默、用户选择出声"这个组合才既有信息量又不吵。
        """
        generated = collect_generated_paths(Config, {"a_memorix": {"integration": {}}})
        data = {"a_memorix": {"integration": {"fuzzy_modify_enabled": True}}}

        with caplog.at_level(logging.WARNING, logger="config.config_lifecycle"):
            hits = check_field_lifecycle(Config, data, file_name=FAKE_FILE, generated_paths=generated)

        assert hits == ["a_memorix.integration.fuzzy_modify_enabled"]
        assert "fuzzy_modify_enabled" in caplog.text

    def test_absent_deprecated_field_is_silent(self, caplog: pytest.LogCaptureFixture) -> None:
        """**反向判据**：文件里没有这条声明时不许出声——否则每次启动都刷一遍。

        这条与上一条必须成对：只有"出现才响"才能让警告保有信息量。
        """
        data = {"a_memorix": {"integration": {"enable_memory_query_tool": True}}}

        with caplog.at_level(logging.WARNING, logger="config.config_lifecycle"):
            hits = check_field_lifecycle(Config, data, file_name=FAKE_FILE)

        assert hits == []
        assert caplog.text == ""

    def test_deprecation_survives_the_real_load_path(self, tmp_path: Path) -> None:
        """走生产入口：带弃用字段的配置**照常加载**（弃用不是拒绝），且日志有点名。

        用 ``ModelConfig`` 的最小夹具（``Config`` 的必填项太多，夹具会盖过判据本身）；
        声明用 ``monkeypatch`` 注入到 ``ModelConfig`` 上（真表里没有条目，见模块 docstring）。
        """
        declaration = FieldLifecycle(
            config_name="ModelConfig",
            path="api_providers.base_url",
            state=FieldLifecycleState.DEPRECATED,
            replacement="api_providers[].url",
            reason="测试：仅用于验证加载路径上的出声行为",
        )
        monkeypatch_declarations = (declaration,)
        import src.config.config_lifecycle as lifecycle_module

        original = lifecycle_module._DECLARATIONS  # noqa: SLF001 — 注入式判据的既有先例
        lifecycle_module._DECLARATIONS = original + monkeypatch_declarations  # noqa: SLF001
        try:
            config_path = tmp_path / "model_config.toml"
            config_path.write_text(
                f"""[inner]
version = "{MODEL_CONFIG_VERSION}"

[[models]]
model_identifier = "probe-4seg-lifecycle"
name = "probe-4seg-lifecycle"
api_provider = "probe"

[[api_providers]]
name = "probe"
base_url = "https://probe.invalid/v1"
api_key = "sk-fake-lifecycle"
auth_type = "bearer"
""",
                encoding="utf-8",
            )

            config, updated = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

            assert config.api_providers[0].base_url == "https://probe.invalid/v1"  # 照常生效
            assert updated is False
        finally:
            lifecycle_module._DECLARATIONS = original  # noqa: SLF001


class TestTemplateBaselineWiring:
    """接线完整性：`.template` 基线真的被落盘、真的被读（否则"默认值静默"只是空谈）。

    ⚠️ 这两条是**接线判据**（`AGENTS §七` #1：新机制必须查生产调用点）：只测
    `collect_generated_paths` 这个纯函数，等于"测试自己 init 自己"——基线文件写没写、
    加载器读没读，都得单独钉住。
    """

    def test_generate_writes_the_template_baseline(self, tmp_path: Path) -> None:
        config_path = tmp_path / "bot_config.toml"

        generate_new_config_file(Config, config_path, CONFIG_VERSION)

        template_path = tmp_path / "bot_config.toml.template"
        assert template_path.exists(), "默认值基线没落盘（抑制集永远是空的）"
        template_data = tomlkit.loads(template_path.read_text(encoding="utf-8")).unwrap()
        # 基线里必须真带着那 6 个弃用键——这正是"用户没改也会看到警告"的来源
        generated = collect_generated_paths(Config, template_data)
        assert "a_memorix.integration.fuzzy_modify_enabled" in generated

    def test_load_reads_the_baseline_and_stays_quiet(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**端到端**：生成默认配置 ⇒ 立刻加载 ⇒ 不出现任何弃用警告（同一条生产路径）。

        这条把"默认值不出声"从**纯函数判据**升级成**接线判据**：若哪天有人忘了在
        `load_config_from_file` 里传 `generated_paths`，本用例当场红。
        """
        config_path = tmp_path / "bot_config.toml"
        generate_new_config_file(Config, config_path, CONFIG_VERSION)

        with caplog.at_level(logging.WARNING, logger="config.config_lifecycle"):
            config, _updated = load_config_from_file(Config, config_path, CONFIG_VERSION)

        assert config is not None
        assert "[配置弃用]" not in caplog.text, f"默认配置就开始刷弃用警告：{caplog.text[:400]}"


# ── 2 · remove 显式拒绝 ──────────────────────────────────────────────


def _removed_declaration(path: str, replacement: str | None) -> FieldLifecycle:
    return FieldLifecycle(
        config_name="Config",
        path=path,
        state=FieldLifecycleState.REMOVED,
        replacement=replacement,
        reason="测试：合成声明，用于验证拒绝形态",
    )


class TestRemoveRefuses:
    """移除期：**拒绝**、指名道姓、原文件不动。"""

    def test_refusal_carries_path_replacement_and_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        declaration = _removed_declaration("chat.legacy_reply_mode", "chat.reply_timing.reply_trigger_mode")
        monkeypatch.setattr(config_lifecycle, "_DECLARATIONS", (declaration,))
        data = {"chat": {"legacy_reply_mode": "hybrid", "max_context_size": 30}}

        with pytest.raises(ConfigFieldRefusedError) as excinfo:
            check_field_lifecycle(Config, data, file_name=FAKE_FILE)

        message = str(excinfo.value)
        assert "chat.legacy_reply_mode" in message
        assert "chat.reply_timing.reply_trigger_mode" in message
        assert FAKE_FILE in message
        # 结构化字段同样可用（调用方不必解析消息）
        assert excinfo.value.path == "chat.legacy_reply_mode"
        assert excinfo.value.replacement == "chat.reply_timing.reply_trigger_mode"
        assert excinfo.value.file_name == FAKE_FILE

    def test_refusal_without_replacement_still_says_so(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """没有替代者时明说"没有替代者"，不许在消息里留空档（读的人会以为是漏写）。"""
        monkeypatch.setattr(config_lifecycle, "_DECLARATIONS", (_removed_declaration("chat.dead_key", None),))

        with pytest.raises(ConfigFieldRefusedError) as excinfo:
            check_field_lifecycle(Config, {"chat": {"dead_key": 1}}, file_name=FAKE_FILE)

        assert "本字段没有替代者" in str(excinfo.value)

    def test_refusal_happens_before_any_write(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """走生产入口：被拒绝时**盘上字节一个都不动**，异常类型化地冒到调用方。

        声明注入到 ``ModelConfig`` 上，路径选一个"模型里真的没有"的键 ⇒ 拒绝必然命中。
        同时钉住"拒绝发生在 ``from_dict`` 之前"——若哪天有人把它挪到 ``from_dict`` 之后，
        这个文件会先被 ``write_config_to_file`` 改写，字节断言当场红。
        """
        declaration = FieldLifecycle(
            config_name="ModelConfig",
            path="api_providers.legacy_endpoint",
            state=FieldLifecycleState.REMOVED,
            replacement="api_providers.base_url",
            reason="测试：合成声明",
        )
        import src.config.config_lifecycle as lifecycle_module

        original = lifecycle_module._DECLARATIONS  # noqa: SLF001
        lifecycle_module._DECLARATIONS = original + (declaration,)  # noqa: SLF001
        try:
            config_path = tmp_path / "model_config.toml"
            # 版本写低一档 ⇒ 若拒绝没拦住，这里会走升级改写（字节必然变），判据就能抓到
            config_path.write_text(
                """[inner]
version = "1.17.0"

[[models]]
model_identifier = "probe-4seg-refuse"
name = "probe-4seg-refuse"
api_provider = "probe"

[[api_providers]]
name = "probe"
base_url = "https://probe.invalid/v1"
legacy_endpoint = "https://old.invalid/v1"
api_key = "sk-fake-refuse"
auth_type = "bearer"
""",
                encoding="utf-8",
            )
            before = config_path.read_bytes()

            with pytest.raises(ConfigFieldRefusedError):
                load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

            assert config_path.read_bytes() == before, "被拒绝的加载仍然改了文件"
        finally:
            lifecycle_module._DECLARATIONS = original  # noqa: SLF001


# ── 3 · 遍历边界 ────────────────────────────────────────────────────


class TestTraversalBoundary:
    """遍历按 schema 结构走：数组元素/嵌套子表能命中，``dict[str, X]`` 根不误报。"""

    def test_hits_inside_list_of_tables(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``[[api_providers]]`` 每一项都要能被查到（数组下标不进路径、返回值按路径去重）。

        返回值去重（1 条路径）**不代表**只查了第一个表项——本用例同时断言日志里两条警告
        （a 与 c 的值各不相同）都在，这样"只看了第一个元素"这种实现缺陷跑不掉。
        """
        declaration = FieldLifecycle(
            config_name="ModelConfig",
            path="api_providers.legacy_endpoint",
            state=FieldLifecycleState.DEPRECATED,
            reason="测试：数组元素内的弃用字段",
        )
        monkeypatch.setattr(config_lifecycle, "_DECLARATIONS", (declaration,))
        data = {
            "api_providers": [
                {"name": "a", "legacy_endpoint": "https://a.invalid"},
                {"name": "b"},
                {"name": "c", "legacy_endpoint": "https://c.invalid"},
            ]
        }

        with caplog.at_level(logging.WARNING, logger="config.config_lifecycle"):
            hits = check_field_lifecycle(ModelConfig, data, file_name=FAKE_FILE)

        assert hits == ["api_providers.legacy_endpoint"]
        warnings = [record.getMessage() for record in caplog.records]
        assert len(warnings) == 2, f"应逐个表项各出一条（a 与 c），实际：{warnings}"
        assert any("https://a.invalid" in item for item in warnings)
        assert any("https://c.invalid" in item for item in warnings)

    def test_dict_root_is_not_descended(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``dict[str, X]`` 的键由数据决定（agent_id 之类）⇒ 不下钻、不误报。

        反例形态：把 ``personality`` 的**值**当"子表继续走"没问题，但**键**不是 schema 的一部分；
        本用例把声明挂在 ``dict`` 根路径上，断言它**不会**因为某个 agent_id 恰好同名而命中。
        """
        declaration = FieldLifecycle(
            config_name="Config",
            path="a_memorix.connectionist.personality.some_field",
            state=FieldLifecycleState.DEPRECATED,
            reason="测试：dict 根下的路径不该被命中",
        )
        monkeypatch.setattr(config_lifecycle, "_DECLARATIONS", (declaration,))
        data = {"a_memorix": {"connectionist": {"personality": {"some_field": {"decay_rate": 1.0}}}}}

        hits = check_field_lifecycle(Config, data, file_name=FAKE_FILE)

        assert hits == [], "dict 根的键被当成 schema 路径下钻了（会误报）"

    def test_undeclared_unknown_keys_are_left_alone(self) -> None:
        """**本段不改变"未知键被丢弃"的老行为**：没声明就没人管（真表的空判据）。"""
        data = {"chat": {"some_key_nobody_declared": 1}}

        assert check_field_lifecycle(Config, data, file_name=FAKE_FILE) == []

    def test_diagnostics_lists_unknown_keys(self) -> None:
        """诊断入口（供对齐账目）：列出 schema 不认的键，含未被声明的。"""
        paths = removed_field_paths(Config, {"chat": {"nope_key": 1, "max_context_size": 30}})

        assert paths == ["chat.nope_key"]


# ── 4 · 声明表自身的机械判据 ────────────────────────────────────────


class TestDeclarationTable:
    """入表纪律：路径必须真的在 schema 里（防拼错字段名造成的"永不命中"）。"""

    def test_every_declared_path_exists_in_schema(self) -> None:
        for declaration in declarations_for(Config) + declarations_for(ModelConfig):
            model_cls = Config if declaration.config_name == "Config" else ModelConfig
            node: object = model_cls
            for part in declaration.path.split("."):
                fields = getattr(node, "model_fields", None)
                assert fields is not None, f"{declaration.path}: {part} 的宿主不是配置模型"
                assert part in fields, f"{declaration.path}: schema 里没有字段 {part}"
                node = fields[part].annotation
                # list[X] / dict[K, V] 继续用元素类型下钻（与遍历逻辑同口径）
                origin = getattr(node, "__origin__", None)
                args = getattr(node, "__args__", ())
                if origin is list and args:
                    node = args[0]
                elif origin is dict and args:
                    node = args[-1]

    def test_declared_states_are_known(self) -> None:
        """状态只允许枚举里的三种——防"写了个字符串凑数"。"""
        for declaration in declarations_for(Config):
            assert isinstance(declaration.state, FieldLifecycleState)

    def test_deprecated_entries_document_why(self) -> None:
        """每条 ``DEPRECATED`` 必须写清理由：没有理由的弃用警告等于噪声。"""
        for declaration in declarations_for(Config):
            if declaration.state is FieldLifecycleState.DEPRECATED:
                assert declaration.reason, f"{declaration.path} 缺 reason"

    def test_no_removed_path_exists_in_schema(self) -> None:
        """**不变量**：``REMOVED`` 声明的路径必须**不在** schema 里。

        为什么这条必须有（它是"抑制集"逼出来的）：`generate_new_config_file` 会把 schema 里
        **每个**字段写进默认配置 ⇒ 若某条 ``REMOVED`` 的路径还在 schema 里，那么**程序自己生成的
        配置就会带一个"已移除"字段** ⇒ 每个用户首启即被拒绝加载（唯一出路是手改模板）。
        ⇒ ``REMOVED`` 的前提是"schema 里已经删掉这个字段"，这条守住它。

        配套含义：``DEPRECATED`` 才允许"字段还在"。一段迁移的正确顺序因此是
        ``加到 DEPRECATED``（字段留）→ 删 schema 字段 → ``改成 REMOVED``（拒绝）。
        """
        for declaration in declarations_for(Config) + declarations_for(ModelConfig):
            if declaration.state is not FieldLifecycleState.REMOVED:
                continue
            model_cls = Config if declaration.config_name == "Config" else ModelConfig
            node: object = model_cls
            missing_at: str | None = None
            for part in declaration.path.split("."):
                fields = getattr(node, "model_fields", None)
                if fields is None or part not in fields:
                    missing_at = part
                    break
                node = fields[part].annotation
                origin = getattr(node, "__origin__", None)
                args = getattr(node, "__args__", ())
                if origin is list and args:
                    node = args[0]
                elif origin is dict and args:
                    node = args[-1]
            assert missing_at is not None, (
                f"{declaration.path} 被声明为 REMOVED，但它仍在 schema 里 —— "
                "程序生成的默认配置会带着这个字段，用户首启即被拒绝"
            )
