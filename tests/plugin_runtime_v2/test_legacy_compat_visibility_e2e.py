"""端到端：老插件因**兼容层不可用**而加载失败 —— **主进程真的能看见**（跨进程 IPC 那一跳）。

## 为什么要有这条
runner 进程刻意关掉控制台日志（`src/plugin_runtime/runner/runner_main.py:2640`
`_disable_runner_console_logging()`）⇒ 它的日志到不了宿主控制台 ⇒ "主进程可见"**完全依赖 IPC 那一跳**。
此前只有**单测层**（(甲)(乙) 3 例）与**结构链**（`runner_main.py:436` 读 `failed_plugins`
→ `:476-481 _notify_ready(...)`）⇒ **跨进程那一跳没有证据**。
（这一类"多跳链上的声称"：结构性判定 + 单测都不算端到端。）

## 判据（lead 2026-10-17 定）
载荷里那条原因 **非空** 且 **能指认"兼容层缺席 / 旧版面导入失败"**；
⛔ **不硬编码一个仓里不存在的字符串**（`兼容层不可用` 这个串全仓不存在——先前的派单凭印象写过它，
故本用例只断言"指认得到"，并把**实测原文**打进输出）。
实测形态由 `_mentions_legacy_compat()` 的判据 + 用例输出共同给出（见 `[e2e] failed_plugin_reasons[...] = ...`）。

## 覆盖到哪一步（如实）
✅ 覆盖：宿主 TCP 监听（`TCPTransportServer`）→ runner 子进程**握手**（`runner.hello` + 会话令牌 + SDK 版本门）
        → runner 侧插件加载失败 → runner 发 `runner.ready` → **宿主 handler 收到载荷**（断言点）
❌ 不覆盖：宿主把这载荷写进日志 / 指标 / 告警的那一跳；也不覆盖 `host/supervisor.py` 的生产装配
        （本用例自己起 `RPCServer`，不经 supervisor）。

## 合成"兼容层缺席"是否真生效（否则"没注入"与"机制没工作"不可分辨）
`sitecustomize.py`（PYTHONPATH 注入）在**子进程里**执行：`sys.modules["maibot_sdk.compat"] = None`
⇒ 子进程 stderr 打 `[e2e-sitecustomize] applied: ...` + 写一个 marker 文件；两条都在用例里断言。
"""
import asyncio
import contextlib
import json
import os
import secrets
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest

from src.plugin_runtime.host.rpc_server import RPCServer
from src.plugin_runtime.protocol.envelope import Envelope
from src.plugin_runtime.transport.tcp import TCPTransportServer


REPO_ROOT = Path(__file__).resolve().parents[2]
READY_TIMEOUT_S = 120.0
LEGACY_PLUGIN_ID = "e2e.legacy-demo"
V2_PLUGIN_ID = "e2e.v2-demo"

# 夹具 manifest：**按宿主校验器认的 v2 schema 写**（`manifest_validator.PluginManifest`）。
#
# ⚠️ 两个现场事实（都不是本用例引入，但都会拦住夹具，故写在这里）：
#   ① 本基点宿主的校验器只收 `manifest_version = 2`
#      （`manifest_validator.py:616 Literal[2]` / `:809 SUPPORTED_MANIFEST_VERSIONS = [2]`），
#      而**树里自带的插件 manifest 全写 3**（`plugins/hello_world_plugin/_manifest.json`、
#      `plugins/maibot-team.v1-compat/_manifest.json`）⇒ 它们在本基点会在 manifest 校验就被拒
#      （实测原文：`manifest 校验失败: Manifest 版本不兼容: manifest_version=3，仅支持 2`）；
#   ② v2 是**另一套 schema**（`_StrictManifestModel` 禁未知字段）：要 `capabilities` / `i18n` /
#      两个 `max_version`，而 **`scopes` 是 v3 的字段、在 v2 里属"存在未声明字段"** ⇒ 不能照抄 hello_world。
#
# 本用例要测的是**兼容层缺席那条链**，故夹具按宿主接受的版本写；① 是另一条线的缺陷，这里只标不改。
_MANIFEST_V2_TEMPLATE: dict[str, Any] = {
    "manifest_version": 2,
    "version": "1.0.0",
    "name": "E2E fixture",
    "description": "E2E 夹具（临时目录内生成，不入库）",
    "author": {"name": "E2E", "url": "https://example.invalid"},
    "license": "GPL-3.0-or-later",
    "urls": {"repository": "https://example.invalid/repo"},
    "host_application": {"min_version": "1.0.0", "max_version": "99.0.0"},
    "sdk": {"min_version": "1.0.0", "max_version": "99.0.0"},
    "capabilities": [],
    "i18n": {"default_locale": "zh_CN", "supported_locales": ["zh_CN"]},
}

# 旧版面（V1）插件：import 的是 src.plugin_system —— 兼容层在场时由导入钩子重定向到 maibot_sdk.compat
_LEGACY_SOURCE = '''"""E2E 夹具：旧版面（V1）插件（只 import src.plugin_system，不做别的事）。"""

from src.plugin_system import BasePlugin


class E2ELegacyDemoPlugin(BasePlugin):
    """兼容层在场时，这一行 import 由 maibot_sdk.compat 的导入钩子接管。"""

    plugin_name = "e2e-legacy-demo"

    def __init__(self) -> None:
        pass

    def get_plugin_components(self):
        """旧版面 `BasePlugin` 的唯一抽象成员——不实现它会变成"抽象类不可实例化"（适配期报错）。"""
        return []


__all__ = ["E2ELegacyDemoPlugin"]
'''

# 反向对照：不依赖旧版面的 V2 插件（create_plugin 工厂 + 三个契约钩子）
def _v2_source(plugin_id: str) -> str:
    """生成一个 V2 插件源码（`create_plugin` 工厂）——内嵌 `plugin_id` 与 manifest 一致。"""
    return f'''"""E2E 反向对照：V2 插件（create_plugin 工厂，不碰旧版面）。"""

from src.plugin_runtime_v2.sdk import MaiBotPlugin


class E2EV2DemoPlugin(MaiBotPlugin):
    plugin_id = "{plugin_id}"
    plugin_version = "1.0.0"

    async def on_load(self) -> None:
        return None

    async def on_unload(self) -> None:
        return None

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        return None


def create_plugin() -> MaiBotPlugin:
    return E2EV2DemoPlugin()
'''


def _mentions_legacy_compat(reason: str) -> bool:
    """原因是否**指认得到**"兼容层缺席 / 旧版面导入失败"（不硬编码单一措辞）。"""
    lowered = reason.lower()
    return "src.plugin_system" in reason or "compat" in lowered or "兼容层" in reason


def _write_plugin(plugin_root: Path, dir_name: str, plugin_id: str, source: str) -> Path:
    """造一个插件目录（`_manifest.json` v2 + `plugin.py`）——loader 的发现形状。

    manifest 形状的取舍见上面 `_MANIFEST_V2_TEMPLATE` 的注释（v2 是宿主校验器认的那套；
    树里自带插件写的 v3 在本基点会被拒，属另一条线的缺陷）。
    """
    plugin_dir = plugin_root / dir_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(_MANIFEST_V2_TEMPLATE)
    manifest["id"] = plugin_id
    manifest["name"] = f"E2E fixture {plugin_id}"
    (plugin_dir / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=4), encoding="utf-8"
    )
    (plugin_dir / "plugin.py").write_text(source, encoding="utf-8")
    return plugin_dir


def _write_sitecustomize(target_dir: Path, marker_file: Path) -> Path:
    """写一个把 `maibot_sdk.compat` 置 None 的 sitecustomize（子进程里自证生效）。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "sitecustomize.py").write_text(
        textwrap.dedent(
            f'''\
            """E2E：合成"兼容层缺席"——`maibot_sdk.compat` 置 None ⇒ 导入即 ImportError。"""
            import sys
            from pathlib import Path

            sys.modules["maibot_sdk.compat"] = None
            _state = "sys.modules['maibot_sdk.compat'] is None"
            print(f"[e2e-sitecustomize] applied: {{_state}}", file=sys.stderr, flush=True)
            Path(r"{marker_file}").write_text(_state, encoding="utf-8")
            '''
        ),
        encoding="utf-8",
    )
    return target_dir


async def _run_runner(
    plugin_roots: Sequence[Path],
    *,
    block_compat: bool,
    tmp_path: Path,
    env_builder: Callable[[int, str, Sequence[Path]], dict[str, str]] | None = None,
) -> dict[str, Any]:
    """起宿主 RPC（§二.2）+ runner 子进程（§二.1 env），收 `runner.ready` 载荷。

    `plugin_roots` 是**插件目录列表**（≥1）：多个目录按 `os.pathsep` 拼成一个 `MAIBOT_PLUGIN_DIRS`
    —— 这正是两侧口径必须一致的那一处（见 `test_two_plugin_dirs_are_both_discovered`）。

    `env_builder`：**用真实 producer 造 env** 的钩子 `(port, token, roots) -> env`。
    缺省时由本函数自己拼（= 只验消费侧）；给了它则由**插件桥**那份实现拼
    ⇒ 这样端到端才**同时**覆盖 producer 与 consumer 两侧的口径（见多目录那条用例）。

    宿主侧除 `runner.ready` 外，还要**补三个回调桩**——否则"激活成功"这条路走不完：
    runner 在激活期会**回调宿主** `plugin.bootstrap`（`runner_main.py:1341`）与
    `plugin.register_components`（`:1456`），桩按真实宿主的语义回 `accepted`（见各自 call site 对响应的判读）。
    桩被调用的次数一并记进 `host_calls`——它是"这次端到端到底走到哪一步"的实物。

    Returns:
        dict: ``payload`` / ``timed_out`` / ``stdout`` / ``stderr`` / ``marker`` / ``host_calls``。
    """
    token = secrets.token_hex(32)
    server = TCPTransportServer(host="127.0.0.1", port=0)
    rpc_server = RPCServer(transport=server, session_token=token)

    loop = asyncio.get_running_loop()
    ready: asyncio.Future[dict[str, Any]] = loop.create_future()
    host_calls: list[str] = []

    async def _on_runner_ready(envelope: Envelope) -> Envelope:
        host_calls.append("runner.ready")
        if not ready.done():
            ready.set_result(dict(envelope.payload))
        return envelope.make_response(payload={"acknowledged": True})

    def _make_stub(method: str):
        async def _stub(envelope: Envelope) -> Envelope:
            host_calls.append(method)
            return envelope.make_response(payload={"accepted": True, "acknowledged": True})

        return _stub

    rpc_server.register_method("runner.ready", _on_runner_ready)
    for method in ("plugin.bootstrap", "plugin.register_components", "plugin.unregister"):
        rpc_server.register_method(method, _make_stub(method))
    await rpc_server.start()

    marker_file = tmp_path / "sitecustomize_applied.txt"
    result: dict[str, Any] = {
        "payload": None,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "marker": None,
        "host_calls": host_calls,
    }

    env = os.environ.copy()
    env["MAIBOT_IPC_ADDRESS"] = f"127.0.0.1:{server._actual_port}"  # start() 之后才有值（port=0 ⇒ 自动分配）
    env["MAIBOT_SESSION_TOKEN"] = token
    # ⚠️ 消费侧口径：runner 按 `os.pathsep` 切分（runner_main.py:2584）。
    #    插件桥那一侧曾是 `",".join`（`compat_bridge.py`）——不一致时多目录会塌成一个；
    #    该处已在本次按"两侧统一"改成 `os.pathsep`，并有跨缝契约用例钉住
    #    （`test_plugin_dirs_env_contract_matches_runner_split`）。
    env["MAIBOT_PLUGIN_DIRS"] = os.pathsep.join(str(root) for root in plugin_roots)
    env["MAIBOT_HOST_VERSION"] = "1.0.0"
    env["MAIBOT_RUNNER_GROUP"] = "e2e"
    env["MAIBOT_EXTERNAL_PLUGIN_IDS"] = ""
    env["MAIBOT_BLOCKED_PLUGIN_REASONS"] = "{}"
    if env_builder is not None:
        # 由**真实 producer**（插件桥）覆盖口径相关的那几个变量 ⇒ 端到端同时覆盖两侧
        env.update(env_builder(server._actual_port, token, plugin_roots))
    result["plugin_dirs_env"] = env["MAIBOT_PLUGIN_DIRS"]  # 台账：**实际**喂给 runner 的那串（不是显示用的拼法）

    if block_compat:
        site_dir = _write_sitecustomize(tmp_path / "sitecustomize_dir", marker_file)
        env["PYTHONPATH"] = str(site_dir) + os.pathsep + env.get("PYTHONPATH", "")

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "src.plugin_runtime.runner.runner_main",
        cwd=str(REPO_ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        result["payload"] = await asyncio.wait_for(ready, timeout=READY_TIMEOUT_S)
    except asyncio.TimeoutError:
        result["timed_out"] = True
    finally:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=20)
        except asyncio.TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
        result["stdout"] = stdout_bytes.decode("utf-8", errors="replace")
        result["stderr"] = stderr_bytes.decode("utf-8", errors="replace")
        result["marker"] = marker_file.read_text(encoding="utf-8") if marker_file.exists() else None
        await rpc_server.stop()

    print(f"\n[e2e] 宿主侧被调用：{host_calls}")
    return result


def _diagnose(result: dict[str, Any], headline: str) -> str:
    """超时/无语料时把子进程两路流原样贴出来（"卡在哪"要有实物）。"""
    return (
        f"{headline}\n"
        f"--- runner stdout（尾 2000 字符）---\n{result['stdout'][-2000:]}\n"
        f"--- runner stderr（尾 2000 字符）---\n{result['stderr'][-2000:]}"
    )


@pytest.mark.asyncio
async def test_legacy_plugin_failure_is_visible_to_host(tmp_path: Path) -> None:
    """**主判据**：兼容层缺席 ⇒ 老插件加载失败 ⇒ 宿主 handler 收到 `failed_plugin_reasons` 且指认得到。"""
    plugin_root = tmp_path / "plugins"
    _write_plugin(plugin_root, "e2e_legacy_demo", LEGACY_PLUGIN_ID, _LEGACY_SOURCE)

    result = await _run_runner([plugin_root], block_compat=True, tmp_path=tmp_path)

    # 合成是否真的生效（子进程内自证：stderr 一行 + marker 文件）
    assert "[e2e-sitecustomize] applied" in result["stderr"], _diagnose(
        result, "sitecustomize 没在子进程里生效 ⇒ 这次测的不是'兼容层缺席'"
    )
    assert result["marker"] == "sys.modules['maibot_sdk.compat'] is None", _diagnose(
        result, "marker 文件内容不对 ⇒ 注入没落地"
    )

    assert not result["timed_out"], _diagnose(result, f"{READY_TIMEOUT_S:.0f}s 内没等到 runner.ready")
    payload = result["payload"]
    assert payload is not None

    reasons = payload.get("failed_plugin_reasons") or {}
    assert reasons.get(LEGACY_PLUGIN_ID), _diagnose(
        result, f"载荷里没有 {LEGACY_PLUGIN_ID} 的原因（failed_plugin_reasons={reasons!r}）"
    )
    reason = str(reasons[LEGACY_PLUGIN_ID])
    print(f"\n[e2e] payload.failed_plugins = {payload.get('failed_plugins')!r}")
    print(f"[e2e] payload.loaded_plugins = {payload.get('loaded_plugins')!r}")
    print(f"[e2e] failed_plugin_reasons[{LEGACY_PLUGIN_ID}] = {reason!r}\n")
    assert _mentions_legacy_compat(reason), (
        f"原因要能指认'兼容层缺席 / 旧版面导入失败'，实测原文：{reason!r}"
    )


@pytest.mark.asyncio
async def test_v2_plugin_loads_and_failure_report_is_empty(tmp_path: Path) -> None:
    """**反向对照 A**：不依赖旧版面的 V2 插件 ⇒ 加载成功、失败集合为空（防"永远报失败"）。"""
    plugin_root = tmp_path / "plugins"
    _write_plugin(plugin_root, "e2e_v2_demo", V2_PLUGIN_ID, _v2_source(V2_PLUGIN_ID))

    result = await _run_runner([plugin_root], block_compat=True, tmp_path=tmp_path)
    assert not result["timed_out"], _diagnose(result, f"{READY_TIMEOUT_S:.0f}s 内没等到 runner.ready")

    payload = result["payload"]
    assert payload is not None
    print(f"\n[e2e] (V2) loaded_plugins = {payload.get('loaded_plugins')!r}")
    print(f"[e2e] (V2) failed_plugin_reasons = {payload.get('failed_plugin_reasons')!r}\n")
    assert V2_PLUGIN_ID in (payload.get("loaded_plugins") or []), _diagnose(
        result, f"V2 插件没被加载：loaded={payload.get('loaded_plugins')!r} payload={payload!r}"
    )
    assert not (payload.get("failed_plugin_reasons") or {}), (
        f"反向对照要求失败集合为空，实测：{payload.get('failed_plugin_reasons')!r}"
    )


@pytest.mark.asyncio
async def test_plugin_without_factory_is_named_in_failures(tmp_path: Path) -> None:
    """**（2026-10-17 改名：旧名 `test_plugin_without_factory_is_invisible_to_host` —— 历史名就这一行）**
    既无 `create_plugin` 也无旧版 BasePlugin 的插件 ⇒ **宿主看得见（失败原因里具名）**。

    ⭐ 翻的时刻 = `silence-first` §3b（2026-10-17，`plugin_loader.py`）：那条兜底从"只打一条 `logger.error`
    然后 `return None`"改成**同时写 `_failed_plugins[plugin_id]`** —— 本用例原 docstring 就写明
    "若'丢弃出声'落地，**本用例应当改成断言它出现在失败原因里**"（届时本用例会红，那正是要的提示）。
    ⇒ 现在它**在 `failed_plugin_reasons` 里**，带一条具名原因；**不再**是"三栏全空"的静默丢弃。

    ⚠️ **名字必须与断言一致**：旧名说的是"看不见"、断言是"看得见" ——
    **名字与断言相反比名字过时更危险**（下一个人按名字读会得出反结论），故**改名**而不是留痕。
    """
    plugin_root = tmp_path / "plugins"
    _write_plugin(
        plugin_root,
        "e2e_no_factory",
        "e2e.no-factory",
        '"""E2E 夹具：既没有 create_plugin 工厂，也没有旧版 BasePlugin 子类。"""\n\nSENTINEL = "e2e-no-factory"\n',
    )

    result = await _run_runner([plugin_root], block_compat=False, tmp_path=tmp_path)
    assert not result["timed_out"], _diagnose(result, f"{READY_TIMEOUT_S:.0f}s 内没等到 runner.ready")

    payload = result["payload"]
    assert payload is not None
    print(f"\n[e2e] (无工厂无旧版) payload = {payload!r}\n")
    # 现状（§3b 之后）：它**在**失败原因里，且原因非空具名（= 丢弃出声，不再是静默丢弃）
    assert "e2e.no-factory" not in (payload.get("loaded_plugins") or []), payload
    assert "e2e.no-factory" in (payload.get("failed_plugins") or []), payload
    reasons = payload.get("failed_plugin_reasons") or {}
    assert str(reasons.get("e2e.no-factory") or "").strip(), payload
    assert "e2e.no-factory" not in (payload.get("inactive_plugins") or []), payload
    # 反向对照：失败集合里**只有**它（没有别的插件被误报 ⇒ 不是"永远报失败"换可见性）
    assert payload.get("failed_plugins") == ["e2e.no-factory"], payload


@pytest.mark.asyncio
async def test_legacy_plugin_loads_when_compat_is_available(tmp_path: Path) -> None:
    """**反向对照 B**：兼容层**在场** ⇒ 同一个老插件经导入钩子加载成功、失败集合为空。"""
    plugin_root = tmp_path / "plugins"
    _write_plugin(plugin_root, "e2e_legacy_demo", LEGACY_PLUGIN_ID, _LEGACY_SOURCE)

    result = await _run_runner([plugin_root], block_compat=False, tmp_path=tmp_path)
    assert not result["timed_out"], _diagnose(result, f"{READY_TIMEOUT_S:.0f}s 内没等到 runner.ready")

    payload = result["payload"]
    assert payload is not None
    print(f"\n[e2e] (compat 在场) loaded_plugins = {payload.get('loaded_plugins')!r}")
    print(f"[e2e] (compat 在场) failed_plugin_reasons = {payload.get('failed_plugin_reasons')!r}\n")
    assert not (payload.get("failed_plugin_reasons") or {}), _diagnose(
        result, f"兼容层在场时不该有失败：{payload.get('failed_plugin_reasons')!r}"
    )
    assert LEGACY_PLUGIN_ID in (payload.get("loaded_plugins") or []), _diagnose(
        result, f"老插件没经兼容层加载成功：loaded={payload.get('loaded_plugins')!r}"
    )


def _bridge_env_builder(port: int, token: str, plugin_roots: Sequence[Path]) -> dict[str, str]:
    """用**插件桥自己的** `build_runner_env` 造 env（= 真实 producer 的口径）。

    ⛔ 本函数**不**复制桥的拼接逻辑（复制就等于把"两侧"变成"三处"，测的还不是真的那一份）。
    """
    from tests._plugin_helpers import import_plugin_module

    bridge = import_plugin_module("maibot-team.v1-compat", "compat_bridge")
    return bridge.build_runner_env(
        listen_port=port,
        session_token=token,
        plugin_dirs=[str(root) for root in plugin_roots],
        host_version="1.0.0",
        runner_group="e2e",
        base_env={},
    )


@pytest.mark.asyncio
async def test_two_plugin_dirs_are_both_discovered(tmp_path: Path) -> None:
    """**派修判据（lead 2026-10-17）**：**两个插件目录时必须都发现**。

    这是分隔符口径不一致的**症状级**判据：两侧不一致时 runner 把整串当成一个目录 ⇒ 插件发现为空；
    ⚠️ **单目录时看不出问题**（"看着在、其实不生效"）⇒ 所以必须有这条**多目录**用例。
    反向自检（单个目录仍正常）由本文件其它 V2 用例覆盖（它们都只给一个目录）。
    """
    root_a = tmp_path / "plugins_a"
    root_b = tmp_path / "plugins_b"
    _write_plugin(root_a, "e2e_v2_a", "e2e.v2-demo-a", _v2_source("e2e.v2-demo-a"))
    _write_plugin(root_b, "e2e_v2_b", "e2e.v2-demo-b", _v2_source("e2e.v2-demo-b"))

    result = await _run_runner(
        [root_a, root_b],
        block_compat=False,
        tmp_path=tmp_path,
        env_builder=_bridge_env_builder,
    )
    assert not result["timed_out"], _diagnose(result, f"{READY_TIMEOUT_S:.0f}s 内没等到 runner.ready")

    payload = result["payload"]
    assert payload is not None
    loaded = payload.get("loaded_plugins") or []
    print(f"\n[e2e] (两个插件目录) MAIBOT_PLUGIN_DIRS（实际喂给 runner 的那串）= {result['plugin_dirs_env']!r}")
    print(f"[e2e] (两个插件目录) loaded_plugins = {loaded!r}")
    print(f"[e2e] (两个插件目录) failed_plugin_reasons = {payload.get('failed_plugin_reasons')!r}\n")
    assert sorted(loaded) == ["e2e.v2-demo-a", "e2e.v2-demo-b"], (
        f"两个插件目录必须**都**被发现：实测 loaded={loaded!r}"
        "（只出一个或全空 = `MAIBOT_PLUGIN_DIRS` 的分隔符口径不一致）"
    )
    assert not (payload.get("failed_plugin_reasons") or {}), payload


@pytest.mark.asyncio
async def test_legacy_plugin_load_fails_until_compat_face_wiring_lands(tmp_path: Path) -> None:
    """**接线前的基线（会翻的用例）**：上游 compat 缺席 + 桥接件兜底面在场 + **宿主接线未落** ⇒ 现在必须**加载失败**。

    ## ⭐ 该翻成什么（2026-10-17 **实测改判**，与最初设想相反）
    原设想："接线一落 ⇒ 翻成断言 `loaded_plugins` 含 `e2e.legacy-demo`"。
    **实测否证了它**：`block_compat=True` 把 `sys.modules['maibot_sdk.compat']` 设成 `None`
    ⇒ `maibot_sdk.compat` **不再是包** ⇒ 本地兜底面 `legacy_face` **也装不上**
    （实测原因原文：`ModuleNotFoundError: No module named 'maibot_sdk.compat.base'; 'maibot_sdk.compat' is not a package`）
    ⇒ 这个场景下插件**不可能**加载成功 ⇒ 照原设想写就是一条**恒假断言**（与 `assert … or True` 同族）。
    ⇒ **正确的翻法 = 保留"具名失败"断言 + 拆掉炸弹分支**（本文件已如此改，见下方断言）。

    ## 场景说明（三个条件）
    ① 上游 `maibot_sdk.compat` **缺席**（sitecustomize 注入 + 生效前置断言）；
    ② 桥接件兜底面在（`plugins/maibot-team.v1-compat/legacy_face.py`）—— 但**①把它连带废掉了**；
    ③ 宿主侧接线**已落**（`plugin_loader.py` 含 `legacy_face`）⇒ 老插件在"兼容层不可用"时走 §3a 的
    **具名失败**（这正是本用例要钉的行为，不再是"接线前的失败态"）。

    ⚠️ 覆盖边界：与主判据同一条链（到"宿主 handler 收到 `runner.ready` 载荷"为止）；
    不覆盖"宿主把载荷写进日志/指标"那一跳，也不覆盖 `host/supervisor.py` 的生产装配。
    """
    plugin_root = tmp_path / "plugins"
    _write_plugin(plugin_root, "e2e_legacy_demo", LEGACY_PLUGIN_ID, _LEGACY_SOURCE)

    # 条件②在、条件③不在：两个事实都断言，免得把"面缺失"误当"接线缺失"。
    face_path = REPO_ROOT / "plugins" / "maibot-team.v1-compat" / "legacy_face.py"
    assert face_path.is_file(), f"桥接件兜底面缺失（条件②不成立）：{face_path}"
    loader_source = (REPO_ROOT / "src" / "plugin_runtime" / "runner" / "plugin_loader.py").read_text(
        encoding="utf-8"
    )
    wiring_landed = "legacy_face" in loader_source

    result = await _run_runner([plugin_root], block_compat=True, tmp_path=tmp_path)
    assert not result["timed_out"], _diagnose(result, f"{READY_TIMEOUT_S:.0f}s 内没等到 runner.ready")

    payload = result["payload"]
    assert payload is not None
    reasons = payload.get("failed_plugin_reasons") or {}
    loaded = payload.get("loaded_plugins") or []
    print(f"\n[e2e] (场景B) 宿主接线已落（plugin_loader.py 含 legacy_face）= {wiring_landed}")
    print(f"[e2e] (场景B) loaded_plugins = {loaded!r}")
    print(f"[e2e] (场景B) failed_plugin_reasons[{LEGACY_PLUGIN_ID}] = {reasons.get(LEGACY_PLUGIN_ID)!r}\n")

    # ⚠️ 2026-10-17（silence-first §3a 落地后）**实测改判**：炸弹分支拆除。原写的"该翻成
    # `LEGACY_PLUGIN_ID in loaded_plugins`"**被实测否证** —— `block_compat=True` 把
    # `sys.modules['maibot_sdk.compat']` 设成 `None`，于是 `maibot_sdk.compat` **不再是包**
    # ⇒ 本地兜底面（`legacy_face`）**也装不上去**（实测原因原文：`ModuleNotFoundError: No module
    # named 'maibot_sdk.compat.base'; 'maibot_sdk.compat' is not a package`）⇒ 插件**不可能**加载成功。
    # ⇒ 正确的翻法是"**保留具名失败断言 + 拆炸弹**"：照原提示写 `in loaded_plugins` 会得到一条
    # **恒假断言**（与 `assert … or True` 同族：看着在、其实永远红/永远绿）。
    assert LEGACY_PLUGIN_ID in (payload.get("failed_plugins") or []), (
        f"接线已落但兼容层被屏蔽 ⇒ 老插件应当**具名失败**：loaded={loaded!r} failed={payload.get('failed_plugins')!r}"
    )
    assert reasons.get(LEGACY_PLUGIN_ID), f"失败必须带原因（不许静默）：{reasons!r}"


def test_plugin_dirs_env_contract_matches_runner_split(tmp_path: Path) -> None:
    """**跨缝契约用例**：插件桥构造的 `MAIBOT_PLUGIN_DIRS` 与 runner 的切分口径必须一致。

    这条**直接**钉住本次修的那处不一致：producer（`plugins/maibot-team.v1-compat/compat_bridge.py`）
    曾用 `","` 拼、consumer（`src/plugin_runtime/runner/runner_main.py`）用 `os.pathsep` 切
    ⇒ 多目录塌成一个、单目录无感。断言"桥的输出按 runner 的口径切分 == 原目录列表"，
    任一侧漂移都会红；不依赖子进程，跑得快。
    """
    from tests._plugin_helpers import import_plugin_module

    bridge = import_plugin_module("maibot-team.v1-compat", "compat_bridge")
    dirs = [str(tmp_path / "plugins_a"), str(tmp_path / "plugins_b")]
    env = bridge.build_runner_env(
        listen_port=1234,
        session_token="e2e-token",
        plugin_dirs=dirs,
        host_version="1.0.0",
        runner_group="e2e",
        base_env={},
    )
    raw = env["MAIBOT_PLUGIN_DIRS"]
    print(f"\n[e2e] 桥构造的 MAIBOT_PLUGIN_DIRS = {raw!r}（os.pathsep={os.pathsep!r}）\n")

    # 消费侧口径（runner_main.py 的 `plugin_dirs_str.split(os.pathsep)`）
    assert [item for item in raw.split(os.pathsep) if item] == dirs, (
        f"两侧分隔符口径不一致：桥给 {raw!r}，按 os.pathsep 切分得不到 {dirs!r}"
    )
    assert raw == os.pathsep.join(dirs), f"旧口径（逗号 join）会在这里红：{raw!r}"
    assert env["MAIBOT_IPC_ADDRESS"] == "127.0.0.1:1234", env
    assert env["MAIBOT_SESSION_TOKEN"] == "e2e-token", env
    assert env["MAIBOT_BLOCKED_PLUGIN_REASONS"] == "{}", env
