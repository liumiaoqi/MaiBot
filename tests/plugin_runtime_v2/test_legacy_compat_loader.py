"""`adapter-hop` 两跳 fallback 的**单元层**判据（(乙)/(丙) + adapter 契约面）。

与跨进程那条（`test_legacy_compat_visibility_e2e.py::…_loads_from_local_face_when_upstream_compat_is_absent`）的分工：
* 那边证**终态**（老插件真被加载）+ 两跳的中间证据（runner 回传日志）+ ⑦；
* 这边证**分支**：上游在场时**不碰**本地面（乙）、本地面取不到时**具名出声且不阻断**（丙），
  以及 `LocalLegacyPluginAdapter` 的转发契约（Host 侧**真会调用**的那几个方法）。

⚠️ 出声的读法：loader 的 `logger` 是 `src.common.logger.get_logger` 返回的 structlog 包装，
`caplog` **抓不到**（实测：`caplog.records` 为空）⇒ 这里给自己的 logger 挂一个小 handler，
照 `plugins/maibot-team.v1-compat/selfcheck_legacy_face.py` 的同法（仓规 TID251 也因此豁免在这条上）。
"""

import asyncio
import importlib.util
import logging  # ruff: ignore[TID251]  只为在测试里捕获 loader 的日志记录（生产日志入口仍走 src.common.logger）
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from src.plugin_runtime.runner import plugin_loader
from src.plugin_runtime.runner.plugin_loader import PluginLoader


FACE_PATH_EXPECTED = (
    Path(plugin_loader.__file__).resolve().parents[3] / "plugins" / "maibot-team.v1-compat" / "legacy_face.py"
)


class _CapturedLogs:
    """给 loader 的 logger 临时挂一个小 handler，收下它的记录（`caplog` 读不到那个 logger）。"""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def __enter__(self) -> "_CapturedLogs":
        self._handler = logging.Handler()
        self._handler.emit = lambda record: self.messages.append(_record_text(record))  # type: ignore[method-assign]
        self._handler.setLevel(logging.DEBUG)
        plugin_loader.logger.addHandler(self._handler)
        return self

    def __exit__(self, *_exc: object) -> None:
        plugin_loader.logger.removeHandler(self._handler)

    def named(self, needle: str) -> list[str]:
        return [message for message in self.messages if needle in message]


def _record_text(record: logging.LogRecord) -> str:
    """把一条记录读成可读文本。

    ⚠️ 本仓的日志经 structlog ⇒ `record.msg` **是一个 event dict**（`{'event': …}`），
    `record.getMessage()` 于是返回 `str(dict)` 那样一坨（第一版断言就是被它绊的）
    ⇒ 有 `event` 键就取它（与 `log_handler._serialize_message` 同口径）。
    """

    if isinstance(record.msg, dict):
        return str(record.msg.get("event", "")) % record.args if record.args else str(record.msg.get("event", ""))
    return record.getMessage()


def _local_face_base() -> type:
    """本地面基类的替身（带标记 ⇒ 走 `_find_local_face_plugin_class` 那条退路）。"""

    class _LocalFaceBase:
        _local_legacy_face_base = True

        def get_plugin_components(self) -> list:
            return []

        async def on_load(self) -> None: ...

        async def on_unload(self) -> None: ...

    return _LocalFaceBase


def _loader_local_face() -> PluginLoader:
    """造一个"本地面已启用"的 loader（= 上游缺席时 `_ensure_compat_hook` 之后的状态）。

    `_compat_source` 是**那条退路的前置门**（`plugin_loader.py:760` 附近）⇒ 单测必须像生产那样
    先把它置成 `"bridge-local"`，否则测的是"门关着"的样子。生产里同一个 loader 实例先
    `_ensure_compat_hook()`、再调 `_try_load_legacy_plugin`，两者之间没有别的写点。
    """

    loader = PluginLoader()
    loader._compat_source = "bridge-local"
    return loader


def _fake_legacy_plugin_class(base: type, class_name: str = "DemoLegacyPlugin") -> tuple[types.ModuleType, type]:
    """造一个"插件模块：里面有一个 `base` 的子类"（形状与 e2e 夹具同）。

    ⚠️ 类的 `__module__` 必须等于模块名：loader 的退路按 `candidate.__module__ == module.__name__`
    认"这个类是本模块定义的"（不这么设，替身类会被那道门挡掉 —— 第一版就是这么红的）。
    """

    module = types.ModuleType("fake_plugin_module")
    legacy_cls = type(class_name, (base,), {"__module__": module.__name__})
    module.__dict__[class_name] = legacy_cls
    return module, legacy_cls


@pytest.fixture
def poisoned_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    """合成"上游 `maibot_sdk.compat` 缺席"（与 e2e 子进程同法：置 None ⇒ 子模块 import 必失败）。

    ⚠️ 只把父模块置 None **不够**（第一版就是这么红的）：只要 `sys.modules` 里还留着
    `maibot_sdk.compat.base.base_plugin` 这类**子模块**，Python 会拿它当已加载的包用
    ⇒ `from maibot_sdk.compat.base.base_plugin import …` 照样成功、毒不生效。
    故这里先把 `maibot_sdk.compat.*` 整族从 `sys.modules` 里摘掉，再置 None（复原交给 monkeypatch）。

    **自证毒生效**：否则"取了本地面"与"上游本来就不在"不可分辨
    （这条是 e2e 里 sitecustomize 自证的单元版）。
    """

    for name in [key for key in list(sys.modules) if key == "maibot_sdk.compat" or key.startswith("maibot_sdk.compat.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "maibot_sdk.compat", None)
    with pytest.raises(ImportError):
        from maibot_sdk.compat.base.base_plugin import BasePlugin  # noqa: F401, PLC0415


def test_hop1_and_hop2_use_local_face_when_upstream_is_absent(poisoned_compat: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """**(甲) 的单元侧**：上游缺席 ⇒ 两跳都取本地面，返回本地面 adapter 实例。"""

    face_base = _local_face_base()
    module, legacy_cls = _fake_legacy_plugin_class(face_base)
    adapter_calls: list[Any] = []

    class _LocalAdapter:
        def __init__(self, legacy_instance: Any) -> None:
            adapter_calls.append(legacy_instance)
            self._legacy = legacy_instance

    provided: dict[str, Any] = {"_BasePlugin": face_base, "LocalLegacyPluginAdapter": _LocalAdapter}
    monkeypatch.setattr(plugin_loader, "_local_face_attr", provided.get)

    with _CapturedLogs() as logs:
        instance = _loader_local_face()._try_load_legacy_plugin(module, "unit.hop")

    assert isinstance(instance, _LocalAdapter), f"两跳应当取本地面 adapter，实测 {instance!r}；日志={logs.messages!r}"
    assert isinstance(adapter_calls[0], legacy_cls), "adapter 应当持有**旧实例**（不是类）"


def test_upstream_present_never_touches_local_face(monkeypatch: pytest.MonkeyPatch) -> None:
    """**(乙) 上游在场 ⇒ 行为不变，而且**不许**去取本地面（哪怕本地面是坏的）。

    做法是把 `_local_face_attr` 换成一个**一被碰就炸**的替身：
    如果两跳里还有任何一条在走上游的情况下顺手取本地面，这条就会红。
    """

    from maibot_sdk.compat.base.base_plugin import BasePlugin as UpstreamBasePlugin  # noqa: PLC0415

    # 上游 `BasePlugin` 是 ABC（`get_plugin_components` 是抽象方法）⇒ 替身必须实现它，
    # 否则红的是"抽象类不可实例化"，而不是我们要测的那件事。
    upstream_cls = type(
        "UpstreamStyleLegacyPlugin",
        (UpstreamBasePlugin,),
        {
            "__module__": "fake_plugin_module_upstream",
            "get_plugin_components": lambda self: [],
        },
    )
    module = types.ModuleType("fake_plugin_module_upstream")
    module.__dict__["UpstreamStyleLegacyPlugin"] = upstream_cls

    def _explode(name: str) -> Any:
        raise AssertionError(f"上游在场时**不该**取本地面（{name}）—— 行为必须不变")

    monkeypatch.setattr(plugin_loader, "_local_face_attr", _explode)

    instance = _loader_local_face()._try_load_legacy_plugin(module, "unit.upstream")

    assert instance is not None, "上游在场时老插件必须仍能被加载（行为不变）"
    assert type(instance).__module__.startswith("maibot_sdk.compat"), f"应当用上游 adapter，实测 {type(instance)!r}"
    assert type(instance._legacy) is upstream_cls  # type: ignore[attr-defined]


def test_face_missing_names_the_reason_and_does_not_raise(poisoned_compat: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """**(丙) 第 1 跳（基类）取不到 ⇒ 具名 `ImportError`（这条跳刻意**抛**，见下）。**

    ⚠️ 两条跳的 (丙) 形态**不一样**，别按一条去写另一条：
    * 第 1 跳**抛** `ImportError`（带 plugin_id + 原始原因）—— 这是 `silence-first §3a` 的既定形态：
      由 `_load_plugins_in_order` 的 `_failed_plugins[plugin_id] = str(e)` 接住（`plugin_loader.py:253-259`）；
    * 第 2 跳**只 warning + `return None`**（更晚才失败，抛出去会把"适配失败"混进"识别失败"）。
    """

    module, _ = _fake_legacy_plugin_class(_local_face_base())
    monkeypatch.setattr(plugin_loader, "_local_face_attr", lambda _name: None)

    with pytest.raises(ImportError) as excinfo:
        _loader_local_face()._try_load_legacy_plugin(module, "unit.missing-face")

    message = str(excinfo.value)
    assert "unit.missing-face" in message, f"异常必须**具名**指认是哪个插件：{message!r}"
    assert "maibot_sdk.compat" in message or "ModuleNotFoundError" in message, (
        f"异常必须带上**原始原因**（不是干巴巴一句'拿不到'）：{message!r}"
    )


def test_adapter_missing_names_the_reason_and_does_not_raise(poisoned_compat: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """**(丙) 第 2 跳（adapter）取不到 ⇒ 同样具名 warning + `return None`。**"""

    face_base = _local_face_base()
    module, _ = _fake_legacy_plugin_class(face_base)
    # 第 1 跳有基类、第 2 跳没有 adapter ⇒ 必须走"缺少 adapter"那条分支
    monkeypatch.setattr(
        plugin_loader,
        "_local_face_attr",
        lambda name: face_base if name == "_BasePlugin" else None,
    )

    with _CapturedLogs() as logs:
        instance = _loader_local_face()._try_load_legacy_plugin(module, "unit.no-adapter")

    assert instance is None
    missing_adapter = [message for message in logs.named("unit.no-adapter") if "adapter" in message]
    assert missing_adapter, f"warning 必须具名且指出缺的是 adapter：{logs.messages!r}"
    assert any(str(FACE_PATH_EXPECTED) in message for message in missing_adapter), (
        f"warning 必须给出**本地面路径**（排障要看的就是它）：{missing_adapter!r}"
    )


def test_local_adapter_forwards_lifecycle_and_exposes_runner_contract() -> None:
    """**adapter 契约面**：逐条对 `runner_main.py` 的调用点（转发生命周期 / 面齐全 / **缺口具名出声**）。

    ⚠️ **面契约已改（2026-10-17，插件 `61021af` 起）**：旧实例没有 `get_plugin_components()` 时，
    本地面**不再返回空集**，而是抛具名缺口 `LocalFaceGapError`（「不许静默」那条纪律）。
    ⇒ 本条断言随之改（**改期望、不改面**）：断那个具名异常与原因，而不是断空集。"""

    face_file = FACE_PATH_EXPECTED
    assert face_file.is_file(), f"本地面不在：{face_file}（这是条件②，缺了就测不了这条）"
    spec = importlib.util.spec_from_file_location("_unit_face_probe", face_file)
    assert spec is not None and spec.loader is not None
    face = importlib.util.module_from_spec(spec)
    # ⭐ 同上：按路径 exec 前先注册（本文件 exec 的正是含顶层 @dataclass 的 legacy_face.py）
    sys.modules[spec.name] = face
    spec.loader.exec_module(face)

    calls: list[str] = []

    class _Legacy:
        config_reload_subscriptions = ["model", "bogus"]

        async def on_load(self) -> None:
            calls.append("on_load")

        async def on_unload(self) -> None:
            calls.append("on_unload")

        async def on_config_update(self, config_data: dict, version: str) -> None:
            calls.append(f"on_config_update:{version}")

    adapter = face.LocalLegacyPluginAdapter(_Legacy())
    assert adapter._legacy.__class__ is _Legacy, "adapter 必须持有**旧实例**"

    asyncio.run(adapter.on_load())
    asyncio.run(adapter.on_unload())
    asyncio.run(adapter.on_config_update("self", {"k": 1}, "2"))
    assert calls == ["on_load", "on_unload", "on_config_update:2"], calls

    with pytest.raises(face.LocalFaceGapError) as excinfo:
        adapter.get_components()
    assert "get_plugin_components" in str(excinfo.value), (
        f"缺口出声必须具名（要能看出缺的是哪个方法）：{excinfo.value}"
    )
    assert adapter.get_config_reload_subscriptions() == ["model"], "只认 bot/model（bogus 必须被滤掉）"
    adapter._set_context(object())  # Runner 注入上下文这一步不许抛
