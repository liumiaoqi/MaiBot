# 补丁：把"老插件静默消失"收成"具名失败"（`silence-first` 第 3 步）

> 落盘：2026-10-17 · 作者 dan-heng（`silence-first`）· **这是"可被人依赖的补丁必须落成文件"那条例矩的第一次执行**
> 目标树：`.agents/worktrees/compat-e2e` · 目标文件：`src/plugin_runtime/runner/plugin_loader.py`
> ⚠️ 本文件是**补丁规格（patch spec）**，不是 `git apply` 的字节级 diff —— 原因见 §0；代码块可直接照抄。

## §0 为什么不是字节级 diff（以及"与回执版"的差异）
* 我上一轮回执里那份**只是文本**（lead 转述后由他人实现，`rg --no-ignore` 找不到我原件）⇒ 树里现有实现是"照转述"的，不是我的原件 ⇒ **无法逐字节 diff**。
* 本轮我**没有读全**树里 `_try_load_legacy_plugin()` 与 `:556` 分支的逐行原文（上下文已到底，不猜写 diff）
  ⇒ 所以本文件给的是**符号级锚点 + 可直接照抄的代码块**。
* **与回执版的差异（以文件为准）**：本文件**新增**了 §3（静默收口），并**不需要**改桥接件的 env 构造（原回执里"可能不必改"这一判断保留）。

## §1 现象（要修的那个）
树里接线后，老插件从"**具名失败**"退化成"**静默消失**"：
`loaded=[]` 且 `failed_plugin_reasons[id] = None` ⇒ 宿主三栏全空。
**卡点在 adapter 那一跳**：`_try_load_legacy_plugin()` 里
`from maibot_sdk.compat.base.base_plugin import BasePlugin as LegacyBasePlugin` ⇒ **正是缺席的那个上游** ⇒
`except ImportError: return None` ⇒ 回到 `:556` 的 `logger.error("…缺少 create_plugin 工厂函数且未检测到旧版 BasePlugin")`
⇒ 而 **runner 的控制台日志被 `_disable_runner_console_logging()` 关掉**（runner 只把日志走 IPC 送宿主）
⇒ **宿主侧什么也看不到**。

## §2 已落地的接线（树里现状，本补丁**不动**它）
* `__init__` 里有 `self._compat_source: str = ""`（树 `:81`）
* `_ensure_compat_hook()` 在**上游 ImportError** 分支尝试 `self._compat_source = self._install_local_legacy_face()`
  （树 `:623-624`）· `_install_local_legacy_face()` 为 `@staticmethod`（树 `:629-630`）
⇒ 这段**保留**；§3 只补"拿不到 adapter 时必须出声"。

## §3 补丁本体（两处，都在 `plugin_loader.py`）

### 3a. `_try_load_legacy_plugin()`：上游缺席 ⇒ **不再 `return None` 了事**，改为具名失败
把该函数里这段（现在的形态）：
```python
        if legacy_cls is None:
            try:
                from maibot_sdk.compat.base.base_plugin import BasePlugin as LegacyBasePlugin
            except ImportError:
                return None
```
改成：
```python
        if legacy_cls is None:
            try:
                from maibot_sdk.compat.base.base_plugin import BasePlugin as LegacyBasePlugin
            except ImportError as exc:
                # ⭐ 静默收口：**拿不到 adapter**（上游缺席且兜底面没接上）必须**具名出声**，
                # 否则这条路径会退化成"插件凭空消失"（宿主三栏全空）。
                raise LegacyCompatUnavailableError(
                    f"旧版插件 {plugin_id} 需要兼容层来识别，但兼容层不可用"
                    f"（{type(exc).__name__}: {exc}）"
                ) from exc
```
> ⚠️ `LegacyCompatUnavailableError` **已在本文件定义**（我上一件加的具名异常）⇒ 直接复用，不新增类型。

### 3b. `:556` 那条兜底 error ⇒ 在"兼容层不可用"时**改成具名失败 + warning**
把
```python
        logger.error(f"插件 {plugin_id} 缺少 create_plugin 工厂函数且未检测到旧版 BasePlugin")
        return None
```
改成：
```python
        if self._compat_hook_error:
            reason = (
                "无法判定是否为旧版插件：兼容层不可用"
                f"（{self._compat_hook_error}）⇒ 该插件既没有 create_plugin 工厂函数，也无法用旧版面识别"
            )
            self._failed_plugins[plugin_id] = reason
            logger.warning("插件 %s %s", plugin_id, reason)
            return None
        logger.error(f"插件 {plugin_id} 缺少 create_plugin 工厂函数且未检测到旧版 BasePlugin")
        self._failed_plugins[plugin_id] = "缺少 create_plugin 工厂函数且未检测到旧版 BasePlugin"
        return None
```
（**两条都写 `_failed_plugins`**：命中兼容层缺失 ⇒ 原因具名；否则 ⇒ 原有原因的**短名**，至少不再是 `None`。）

## §4 判据（`silence-first` 第 3 步的两条，必须都有原文）
* **(甲)** 合成"上游缺席 + 兜底面在" ⇒ 真跨进程跑 ⇒ 宿主侧 `failed_plugin_reasons[id]` **非空且具名**（**不许 `None`**）
* **(乙)** **反向自检**：正常场景（上游在场、V2 插件）**不许**因为 §3 新增而产生任何 `warning`/`failed` 条目
  —— 别把"永远报失败"当可见性（同族：不能靠"永远报警"换可见）。

## §5 跑之前（踩过的坑）
树里 `.pyc` 新鲜度显示 **05:53–05:55 有人在跑**（`legacy_face` / `plugin_loader` / 那个 e2e 用例）
⇒ 跑之前**清 `__pycache__`** 或用**新解释器**，否则会读到旧字节码（本会话已踩过一次 `.pyc` 坑）。

## §6 交给下一步
* 本文件 + §3 的两处改动 = **一轮可完成**（改完跑 §4 两条 + `tests/plugin_runtime_v2/test_legacy_compat_visibility_e2e.py`）
* ⛔ 主仓 `src/` 不动（本补丁只作用于**树里**那份；主仓由 lead 按 #7 merge 带入）
