# noqa TID251 整体对象遗留分类报告

> SSD-13 产出 | 仅评估不实施 | 2026-07-25

## 总览

23 处 noqa TID251 分为 3 类：

| 分类 | 数量 | 处理策略 |
|------|------|---------|
| 适配器层合法导入 | 4 | 不处理（适配器是唯一允许导入具体类的地方） |
| 过渡期兼容回退 | 1 | 可立即拆解（SSD-12 已建 registry，回退路径不再触发） |
| 整体对象 | 18 | 见下方三类评估 |

适配器层 4 处（`src/core/adapters/app_config_port.py:338/342/346/350`）+ 过渡期 1 处（`service_task_resolver.py:24`）= 5 处不在本次评估范围。

## 18 处整体对象分类

### 可立即拆解（5 处）

| # | 文件:行号 | 导入目标 | 访问属性 | 拆解方案 |
|---|----------|---------|---------|---------|
| 1 | `emoji_manager.py:21` | `config_manager` | `get_model_config().model_task_config.vlm.model_list` + `register_reload_callback`/`unregister_reload_callback` | 3 个调用点均可被已建的 `ModelConfigPort.get_task_config("vlm")` + `register/unregister_reload_callback()` 覆盖 |
| 3 | `expression_selector.py:17` | `model_config` | `model_task_config.embedding.model_list` | 已有 `ModelConfigPort.get_task_config("embedding")` 可覆盖 |
| 5 | `reply.py:12` | `config_module` | 无 — 导入后未使用 | 直接删除导入即可 |
| 14 | `remote.py:9` | `MMC_VERSION` | 构建时常量 | 通过 `AppConfigPort.get_mmc_version()` 暴露，或保留 noqa（常量导入风险极低） |
| 18 | `service_task_resolver.py:24` | `config_manager` | 过渡期兼容回退 | SSD-12 已建 `model_config_port_registry`，回退路径不再触发，可安全删除 |

### 需新增 Port 方法（7 项，其中 #15 + #17 关联）

| # | 文件:行号 | 导入目标 | 访问属性 | 所需新增 |
|---|----------|---------|---------|---------|
| 2 | `mode_utils.py:2` | `config_manager` | `get_model_config()` 整体对象 + `getattr(model_task_config, task_name)` 动态遍历 | `ModelConfigPort.list_task_names()` + `get_model_by_name(name)` |
| 4 | `send_emoji.py:18` | `config_manager` | `get_model_config().model_task_config.emoji.model_list` + 动态 `getattr` | `ModelConfigPort.has_task_config(task_name)` 或 `get_task_config_dynamic(task_name)` |
| 9 | `supervisor.py:14` | `global_config` | `plugin_runtime` 多属性（enabled/ipc_socket_path/plugin_dirs/local_plugin_sdk_path 等） | 扩展 `PluginRuntimeSnapshot` 补充缺失字段，或新增 `PluginRuntimePort` |
| 10 | `api.py:16` | `global_config` | `maim_message` 整体对象（5+ 属性：ws_server_host/port 等） | `AppConfigPort` 新增 `get_maim_message_config()` → `MaimMessageSnapshot` |
| 12 | `emoji_cache_cleanup.py:313` | `global_config` | `emoji.cache_cleanup` 整体对象（5+ 属性 + 整体传递给 `run_emoji_cache_cleanup(config)`） | 新增 `EmojiCacheCleanupSnapshot` + `AppConfigPort.get_emoji_cache_cleanup_config()` |
| 13 | `image_cache_cleanup.py:283` | `global_config` | `visual.image_cache_cleanup` 整体对象（同 #12 模式） | 新增 `ImageCacheCleanupSnapshot` + `AppConfigPort.get_image_cache_cleanup_config()` |
| 15+17 | `runtime.py:25` + `utils_config.py:6` | `global_config` | `expression`/`experimental`/`jargon`/`reply_style`/`a_memorix` 多域混合 | `ExpressionConfigUtils`/`BehaviorConfigUtils` 等工具类需迁移到 Port，关联 2 文件 |

### 暂不可拆解（6 处）

| # | 文件:行号 | 导入目标 | 不可拆解原因 |
|---|----------|---------|------------|
| 6 | `routes.py:14` | `heartflow_manager` | WebUI 路由直接操作 `heartflow_chat_list` 字典（遍历/查询/修改），需完整字典操作接口 |
| 7 | `routes.py:38/583` | `global_config` | WebUI 配置管理页面需直接操作配置对象（读写），`ChatConfigPort` 是只读接口 |
| 8 | `config.py:20` | `config_manager` | WebUI 配置管理页面是配置的"管理面"（CRUD + 热重载 + 类型反射），Port 是只读"使用面" |
| 11 | `core.py:7` | `global_config` | 点号分隔路径动态反射访问（`_get_nested_config_value(global_config, key)`），属性路径运行时决定 |
| 16 | `runtime.py:2237` | `global_config` | `MCPConfig` 整体传递给 `MCPManager.from_app_config()`，结构复杂且作为整体消费 |

## 汇总

| 分类 | 数量 | 占比 |
|------|------|------|
| 可立即拆解 | 5 | 28% |
| 需新增 Port 方法 | 7 | 39% |
| 暂不可拆解 | 6 | 33% |
| **合计** | **18** | 100% |

## 建议优先级

1. **可立即拆解 5 处** → 下一个 SSD 顺手做掉（改动量小，无架构风险）
2. **需新增 Port 方法 7 处** → 按配置域分批：缓存清理（#12+#13）→ 模型动态查询（#2+#4）→ 多域混合（#15+#17）→ plugin_runtime 快照扩展（#9）→ maim_message 快照（#10）
3. **暂不可拆解 6 处** → 保留 noqa，WebUI 相关的 3 处需要管理面接口重新设计，反射访问和 MCPConfig 整体传递需要架构层面方案
