# 记忆系统与核心架构差距 — 编码任务清单

> 对齐 spec.md 29 项差距 + design.md 增量方案 + CC 审查 7 个修改点。
> 提交归属标记：[CC] = CodeArts 审查/文档，[WB] = WorkBuddy 编码执行，[CA] = CodeArts 架构守卫，[MC] = 主程序变更

---

## 批次总览

| 批次 | 目标 | 覆盖差距 | 前置依赖 |
|------|------|---------|---------|
| 1 | 异常暴露 + 适配器单例化 | G26, G13, G14, G29, G27 | 无 |
| 2 | 数据类型下放 common 层 + 核心模型扩展 | G15, G10, G11 | 第 1 批 |
| 3 | 新增 6 个 Protocol 方法 + host_service 分发补全 | G1-G6, G18, G21 | 第 2 批 |
| 4 | ThinkContext 扩展 + 直觉接入思考循环 | G20, G12 | 第 3 批 |
| 5 | 心跳维护接入核心调度 | G25 | 第 3 批 |
| 6 | ingest_text 全链路删除 + 情绪联动 | G7, G17 | 第 2 批 |

**CC 审查修改点映射**：
1. ~~heartbeat_maintenance 不存在~~ → 已在 MemoryField 实现（line 218），host_service 缺分支 → 第 3 批补
2. 本地镜像类型是死路 → 数据类型下放 common 层 → 第 2 批
3. 第 2+6 批合并 → 类型定义和 A_memorix 解耦同一批完成 → 第 2 批
4. is_temporary bool → 异常子类体系 → 第 1 批
5. observe_experience 统一用 ObserveRequest → 第 2 批
6. ingest_text 全链路彻底删除 → 独立第 6 批
7. 第 1 批不拆分，一次性移除 try-except → 第 1 批

---

## 1. 异常暴露 + 适配器单例化（P0 基础设施）

**目标**：消除适配器层和中间层异常吞没，建立异常子类体系 + 单例模式，为后续新增方法提供正确的基础设施。

**覆盖差距**：G26（适配器层 8 处吞没异常）、G13（12 处独立实例化）、G14（延迟导入）、G29（中间层 21 处兜底）、G27（返回 None 语义模糊）

**批间依赖**：无前置依赖，所有后续批次依赖本批次完成

### 1.1 新增异常子类体系

- [ ] 在 `src/core/types.py` 中新增异常基类 `MemoryServiceError(Exception)`，含 `message: str`、`original: Exception | None` 属性
- [ ] 新增 `TemporaryMemoryError(MemoryServiceError)` — 可重试的临时性错误（网络/超时/服务暂时不可用）
- [ ] 新增 `PermanentMemoryError(MemoryServiceError)` — 不可恢复错误（配置错误/数据损坏）
- [ ] 新增 `MemoryNotFoundError(MemoryServiceError)` — 查询目标不存在（画像/记忆条目）
- [ ] 在 `src/core/types.py` 的 `__all__` 导出列表中添加三个异常类

**验证**：`from src.core.types import TemporaryMemoryError, PermanentMemoryError, MemoryNotFoundError` 可正常导入；`isinstance(TemporaryMemoryError("test"), MemoryServiceError)` 为 True

### 1.2 适配器单例化 + 构造注入

- [ ] 在 `src/core/adapters/memory_service.py` 中新增模块级单例获取函数 `get_memory_service_port() -> AMemorixMemoryServicePort`，内部使用模块级变量 `_instance` 保证全局唯一
- [ ] 新增 `reset_memory_service_port()` 函数供测试 teardown 使用
- [ ] 重构 `AMemorixMemoryServicePort.__init__()` 接受可选的 `memory_service` 参数（构造注入），移除所有方法内的 `from src.services.memory_service import memory_service` 延迟导入
- [ ] 在 `src/core/adapters/__init__.py` 中导出 `get_memory_service_port`，移除 `AMemorixMemoryServicePort` 的直接导出（改为通过工厂函数获取）

**验证**：多次调用 `get_memory_service_port()` 返回同一实例；适配器方法内无 `from src.services.memory_service import memory_service` 延迟导入

### 1.3 12 处调用方迁移至全局单例

- [ ] `src/maisaka/agent_autonomy/agent.py`（2 处：line 85, line 186）：将 `AMemorixMemoryServicePort()` 替换为 `get_memory_service_port()`
- [ ] `src/maisaka/chat_loop_service.py`（1 处：line 785）：同上
- [ ] `src/webui/routers/agent.py`（1 处：line 925）：同上
- [ ] `src/main.py`（1 处：line 266）：同上
- [ ] `src/maisaka/agent_autonomy/prompt_builder.py`（1 处：line 201）：同上
- [ ] `src/maisaka/agent_autonomy/orchestrator.py`（2 处：line 146, line 236）：同上
- [ ] `src/maisaka/builtin_tool/context.py`（1 处：line 85）：同上
- [ ] `src/maisaka/memory/heuristic_injector.py`（1 处：line 71）：同上
- [ ] `src/maisaka/memory/person_profile.py`（1 处：line 24）：同上
- [ ] `src/maisaka/utils/tool_post_execution.py`（1 处：line 63）：同上

**验证**：`rg "AMemorixMemoryServicePort\(\)" src/` 返回 0 结果；所有调用方通过 `get_memory_service_port()` 获取实例

### 1.4 适配器异常策略重构 — 一次性移除所有 try-except

- [ ] 重构 `AMemorixMemoryServicePort.search()`（line 68）：移除 `except Exception` 吞没，网络/超时错误包装为 `TemporaryMemoryError`，其他包装为 `PermanentMemoryError`
- [ ] 重构 `AMemorixMemoryServicePort.get_person_profile()`（line 80）：移除 `except Exception` 吞没；不存在时返回空字典 `{}`，查询失败时抛出 `PermanentMemoryError`
- [ ] 重构 `AMemorixMemoryServicePort.profile_admin()`（line 89）：移除 `except Exception`，失败时抛出 `PermanentMemoryError`
- [ ] 重构 `AMemorixMemoryServicePort.maintain_memory()`（line 155）：移除 `except Exception`，失败时抛出 `PermanentMemoryError`
- [ ] 重构 `AMemorixMemoryServicePort.delete_admin()`（line 164）：移除 `except Exception`，失败时抛出 `PermanentMemoryError`
- [ ] 重构 `AMemorixMemoryServicePort.enqueue_feedback_task()`（line 185）：移除 `except Exception`，失败时抛出 `PermanentMemoryError`
- [ ] 重构 `AMemorixMemoryServicePort.set_memory_personality()`（line 200）：移除 `except Exception`，失败时抛出 `PermanentMemoryError`
- [ ] 重构 `AMemorixMemoryServicePort.ingest_text()`（line 136）：移除 `except Exception`，失败时抛出 `PermanentMemoryError`（本批次暂保留方法签名，第 6 批全链路删除）
- [ ] 重构 `AMemorixMemoryServicePort.observe_experience()`：确认无隐式吞没，异常完整上浮

**验证**：`rg "except Exception" src/core/adapters/memory_service.py` 返回 0 结果

### 1.5 中间层异常透传 — 一次性移除所有 try-except

- [ ] 重构 `src/services/memory_service.py` 全部 21 处 `except Exception`：移除吞没，让异常传播到适配器层
- [ ] 具体方法清单（按行号）：search (130), get_person_profile (153), maintain_memory (191), profile_admin (240), delete_admin (254), ingest_text (306), migration_ingest_text (314), observe (321), migration_search (328), migration_get_person_profile (335), migration_build_profile_injection_text (342), enqueue_feedback_task (349), register_agent (356), get_memory_stats (363), get_all_person_profiles (370), get_person_profile_by_name (377), search_memory (384), ingest_summary (391), get_conversation_history (402), get_recent_conversations (429), get_memory_detail (444)
- [ ] 保留合理的 fire-and-forget 场景（如有后台清理任务），但必须加 ERROR 级别日志

**验证**：`rg "except Exception" src/services/memory_service.py` 仅剩 fire-and-forget 场景（如有），核心方法不再吞没异常

### 1.6 调用方异常处理适配

- [ ] `src/maisaka/agent_autonomy/experience_writer.py`：`write_experience()` 的 `asyncio.create_task` 中捕获 `MemoryServiceError`，记录错误但不重试（fire-and-forget 模式）
- [ ] `src/maisaka/agent_autonomy/orchestrator.py`：搜索/画像调用处捕获 `TemporaryMemoryError` 降级为空结果，`PermanentMemoryError` 记录 error 日志
- [ ] `src/maisaka/agent_autonomy/agent.py`：记忆检索调用处捕获 `TemporaryMemoryError` 降级为空记忆片段，`PermanentMemoryError` 记录 error
- [ ] `src/main.py`：心跳调度处捕获 `TemporaryMemoryError` 跳过本次心跳，`PermanentMemoryError` 记录 error

**验证**：启动后正常工作；模拟 memory_service 异常时，调用方不崩溃，错误完整记录到日志

---

## 2. 数据类型下放 common 层 + 核心模型扩展 + A_memorix 解耦

**目标**：将纯数据类型从 `src/core/types.py` 下放到 `src/common/`，core 和 A_memorix 都从 common 导入，一次性消除 5 处反向依赖。同时扩展核心数据模型。

**覆盖差距**：G15（A_memorix/core/ 反向依赖 5 处）、G10（MemoryWriteResult 缺字段）、G11（RecallItem 不暴露）、G9（observe_experience 参数不统一）、G8（search 参数语义偏移）、G27（get_person_profile 返回 None）

**批间依赖**：依赖第 1 批完成（异常策略 + 单例化）

**CC 审查关键决策**：不要创建本地镜像类型（`_types.py`），把纯数据类型下放到 common 层。这是唯一正确的解耦方向——core 持有 Protocol 和业务语义，common 持有纯数据结构。

### 2.1 创建 `src/common/memory_types.py`

- [ ] 新建 `src/common/memory_types.py`，从 `src/core/types.py` 迁移以下纯数据类型：
  - `MemoryHit` — 搜索命中项（content/score/hit_type/source/hash_value/metadata/episode_id/title）
  - `MemorySearchResult` — 搜索结果（summary/hits/filtered/success/error）
  - `MemoryWriteResult` — 写入结果（success/stored_ids/skipped_ids/detail/pending/trace_id + 新增 observation_id/concept_names）
  - `RecallItem` — 概念召回项（concept/activation/valence/detail_level/relative_time）
  - `IntuitionContext` — 直觉触发结果（frozen: triggered_entries/triggered_episodes/triggered_sagas/cached_entities/token_estimate）
  - `RecallResult` — 召回结果（recall_items/intuition）
  - `ProfileView` — 画像实时视图（subject/observer/associations/voices/contradictions/timeline/depth/episodes/sagas）
  - `ReflectResult` — 反思结果（subject/agent_id/voices/contradictions）
- [ ] 在 `MemoryWriteResult` 中新增 `observation_id: str = ""` 和 `concept_names: list[str] = field(default_factory=list)` 字段
- [ ] 在 `src/common/memory_types.py` 中定义 `__all__` 导出列表
- [ ] 在 `src/common/__init__.py` 中导出 `memory_types` 模块

**验证**：`from src.common.memory_types import MemoryHit, RecallItem, ProfileView` 可正常导入；所有字段使用基础类型（str/dict/tuple/float），不依赖 A_memorix 枚举

### 2.2 迁移 `src/core/memory_utils.py` → `src/common/memory_utils.py`

- [ ] 将 `src/core/memory_utils.py`（68 行）整体移动到 `src/common/memory_utils.py`
- [ ] 更新 `src/common/memory_utils.py` 的导入：从 `from src.core.types import ...` 改为 `from src.common.memory_types import ...`
- [ ] 删除 `src/core/memory_utils.py`

**验证**：`from src.common.memory_utils import coerce_search_result, coerce_write_result` 可正常导入

### 2.3 `src/core/types.py` 改为从 common 重新导出

- [ ] 在 `src/core/types.py` 中删除 `MemoryHit`、`MemorySearchResult`、`MemoryWriteResult` 的类定义，改为 `from src.common.memory_types import MemoryHit, MemorySearchResult, MemoryWriteResult, RecallItem, IntuitionContext, RecallResult, ProfileView, ReflectResult`
- [ ] 保留 `src/core/types.py` 中的非纯数据类型（如 `ThinkContext`、`ObserveRequest` 等业务语义类型）
- [ ] 确保 `src/core/types.py` 的 `__all__` 导出列表不变（向后兼容）

**验证**：`from src.core.types import MemoryHit, RecallItem` 仍可正常导入（重新导出）；现有代码零修改

### 2.4 A_memorix/core/ 反向依赖消除 — 切换到 common 导入

- [ ] `src/A_memorix/core/migration/migration_router.py`（line 6-7）：
  - `from src.core.memory_utils import coerce_search_result, coerce_write_result` → `from src.common.memory_utils import coerce_search_result, coerce_write_result`
  - `from src.core.types import MemoryHit, MemorySearchResult, MemoryWriteResult` → `from src.common.memory_types import MemoryHit, MemorySearchResult, MemoryWriteResult`
- [ ] `src/A_memorix/core/migration/translator.py`（line 6）：
  - `from src.core.types import MemoryHit, MemorySearchResult` → `from src.common.memory_types import MemoryHit, MemorySearchResult`
- [ ] `src/A_memorix/core/connectionist/async_write_queue.py`（line 14）：
  - `from src.core.types import MemoryWriteResult` → `from src.common.memory_types import MemoryWriteResult`
- [ ] `src/A_memorix/core/runtime/sdk_memory_kernel.py`（line 13）：
  - `from src.core.protocols import SessionInfoPort` → 通过 `AMemorixServicePorts` 注入；在 `AMemorixServicePorts` 中新增 `session_info_port` 字段

**验证**：`rg "from src\.core" src/A_memorix/core/` 返回 0 结果；ruff TID251 对所有子目录生效

### 2.5 其他调用方导入路径更新

- [ ] 更新 `src/services/memory_service.py` 中对 `MemoryHit`/`MemorySearchResult`/`MemoryWriteResult` 的导入：改为从 `src.common.memory_types` 导入
- [ ] 更新 `src/core/adapters/memory_service.py` 中对 `MemoryWriteResult` 的导入：改为从 `src.common.memory_types` 导入
- [ ] 更新 `src/core/memory_utils.py` 的所有调用方（如果有其他文件导入它）：改为从 `src.common.memory_utils` 导入
- [ ] 更新 ruff TID251 守卫配置，确保覆盖 `src/A_memorix/core/migration/` 和 `src/A_memorix/core/runtime/` 子目录

**验证**：`rg "from src\.core\.memory_utils" src/` 返回 0 结果；`rg "from src\.core\.types import.*MemoryHit" src/` 仅剩 `src/core/types.py` 自身的重新导出

### 2.6 observe_experience() 签名变更 — 统一用 ObserveRequest

- [ ] 在 `src/core/protocols.py` 中变更 `MemoryServicePort.observe_experience()` 签名：参数从关键字参数改为 `request: ObserveRequest`，返回值类型不变
- [ ] 在 `src/core/adapters/memory_service.py` 中适配新签名：从 `ObserveRequest` 解包参数调用 `memory_service.observe()`，将 `ObserveResult` 的 `observation_id` 和 `concept_names` 填入 `MemoryWriteResult`
- [ ] 迁移 `src/maisaka/agent_autonomy/experience_writer.py`：`write_experience()` 中构造 `ObserveRequest` 对象替代关键字参数
- [ ] 迁移其他调用方（如有直接调用 observe_experience 的地方）

**验证**：`observe_experience(ObserveRequest(text="test"))` 正常工作；返回的 `MemoryWriteResult` 含 `observation_id` 和 `concept_names`

### 2.7 search() 参数扩展

- [ ] 在 `src/core/protocols.py` 的 `MemoryServicePort.search()` 中新增 `agent_id: str = ""` 参数（默认空字符串，向后兼容）
- [ ] 在 `src/core/adapters/memory_service.py` 的 `search()` 中适配新参数：`agent_id` 优先传给 `migration_search()`，`person_id` 保留用于画像查询场景
- [ ] 在 `src/services/memory_service.py` 的 `migration_search()` 中确保 `agent_id` 参数正确传递

**验证**：`search("query", agent_id="silver_wolf")` 正确传递 agent_id；旧调用 `search("query", person_id="user1")` 不受影响

### 2.8 get_person_profile() 返回值语义变更

- [ ] 在 `src/core/protocols.py` 中变更 `get_person_profile()` 返回值类型：从 `Optional[dict[str, Any]]` 改为 `dict[str, Any]`，文档注明"不存在时返回空字典，失败时抛出 MemoryNotFoundError"
- [ ] 在 `src/core/adapters/memory_service.py` 中适配：不存在时返回 `{}`，查询失败时抛出 `PermanentMemoryError`
- [ ] 更新所有调用方的 None 检查逻辑：`if result is None` → `if not result`

**验证**：`get_person_profile("不存在的人")` 返回 `{}`（非 None）；查询失败时抛出 `PermanentMemoryError`

---

## 3. 新增 6 个 Protocol 方法 + host_service 分发补全

**目标**：在 MemoryServicePort 中新增 recall/recall_with_intuition/derive_profile/reflect/weave_narrative/heartbeat_maintenance，补全 host_service 缺失的 2 个分发分支。

**覆盖差距**：G1（缺失直觉召回接口）、G2（缺失连接主义召回接口）、G3（缺失画像实时视图接口）、G4（缺失心跳维护接口）、G5（缺失叙事编织接口）、G6（缺失反思接口）、G18（agent_id 参数传递）、G21（叙事弧暴露）

**批间依赖**：依赖第 2 批完成（common 层数据模型 + A_memorix 解耦）

**事实核实**：MemoryField 已实现全部 6 个方法（recall/recall_with_intuition/derive_profile/reflect/weave_narrative/heartbeat_maintenance）。host_service 已有 recall/derive_profile/reflect/narrative_weave/intuition_trigger 分支，**缺失** heartbeat_maintenance 和 recall_with_intuition 分支。

### 3.1 新增 Protocol 方法定义

- [ ] 在 `src/core/protocols.py` 的 `MemoryServicePort` 中新增 `recall()` 方法定义：参数 `seeds: list[str]`、`agent_id: str = ""`、`min_weight: float = 0.05`、`max_results: int = 20`，返回 `list[RecallItem]`
- [ ] 新增 `recall_with_intuition()` 方法定义：参数 `seeds: list[str]`、`context_text: str`、`agent_id: str = ""`、`min_weight: float = 0.05`、`max_results: int = 20`、`max_tokens: int = 800`，返回 `RecallResult`
- [ ] 新增 `derive_profile()` 方法定义：参数 `subject: str`、`observer: str = ""`，返回 `ProfileView`
- [ ] 新增 `reflect()` 方法定义：参数 `subject: str`、`agent_id: str = ""`，返回 `ReflectResult`
- [ ] 新增 `weave_narrative()` 方法定义：参数 `agent_id: str = ""`，返回 `dict[str, Any]`
- [ ] 新增 `heartbeat_maintenance()` 方法定义：参数 `agent_id: str = ""`、`elapsed_hours: float = 1.0`，返回 `dict[str, Any]`

**验证**：Protocol 定义完整，6 个新方法签名与 design.md 一致

### 3.2 适配器层新增 6 个方法实现

- [ ] 在 `src/core/adapters/memory_service.py` 中实现 `recall()`：调用 `memory_service` 新增的 `recall()` 方法，将 A_memorix 内部 `RecallItem` 翻译为 common 层 `RecallItem`
- [ ] 实现 `recall_with_intuition()`：调用 `memory_service` 新增的 `recall_with_intuition()` 方法，翻译直觉触发结果为 common 层 `IntuitionContext`
- [ ] 实现 `derive_profile()`：调用 `memory_service` 新增的 `derive_profile()` 方法，翻译 A_memorix `ProfileView` 为 common 层 `ProfileView`
- [ ] 实现 `reflect()`：调用 `memory_service` 新增的 `reflect()` 方法，翻译 A_memorix `ReflectResult` 为 common 层 `ReflectResult`
- [ ] 实现 `weave_narrative()`：调用 `memory_service` 新增的 `weave_narrative()` 方法
- [ ] 实现 `heartbeat_maintenance()`：调用 `memory_service` 新增的 `heartbeat_maintenance()` 方法

**验证**：6 个适配器方法均可通过 Protocol 接口调用；异常不吞没，上浮 `MemoryServiceError` 子类

### 3.3 中间层新增 6 个方法

- [ ] 在 `src/services/memory_service.py` 中新增 `recall()` 方法：调用 `self._invoke("recall", payload)`，不吞没异常
- [ ] 新增 `recall_with_intuition()` 方法：调用 `self._invoke("recall_with_intuition", payload)`，不吞没异常
- [ ] 新增 `derive_profile()` 方法：调用 `self._invoke("derive_profile", payload)`，不吞没异常
- [ ] 新增 `reflect()` 方法：调用 `self._invoke("reflect", payload)`，不吞没异常
- [ ] 新增 `weave_narrative()` 方法：调用 `self._invoke("narrative_weave", payload)`，不吞没异常
- [ ] 新增 `heartbeat_maintenance()` 方法：调用 `self._invoke("heartbeat_maintenance", payload)`，不吞没异常

**验证**：中间层方法无 `except Exception` 兜底；异常传播到适配器层

### 3.4 host_service 分发层补全缺失分支

- [ ] 在 `src/A_memorix/host_service.py` 的 `_dispatch()` 中新增 `"heartbeat_maintenance"` 分支：调用 `kernel._memory_field.heartbeat_maintenance(agent_id=..., elapsed_hours=...)`
- [ ] 在 `_dispatch()` 中新增 `"recall_with_intuition"` 分支：调用 `kernel._memory_field.recall_with_intuition(seeds=..., context_text=..., agent_id=..., max_tokens=...)`
- [ ] 确认已有分支正常：`"recall"` (line 344)、`"derive_profile"` (line 356)、`"reflect"` (line 367)、`"narrative_weave"` (line 421)、`"intuition_trigger"` (line 448)
- [ ] 在 `host_service` 的超时组件列表（line 847 附近）中添加 `"heartbeat_maintenance"` 和 `"recall_with_intuition"`

**验证**：`host_service.invoke("heartbeat_maintenance", payload)` 和 `host_service.invoke("recall_with_intuition", payload)` 可正常调用 MemoryField 对应方法

### 3.5 端到端集成验证

- [ ] 编写验证脚本或手动测试：通过 `get_memory_service_port()` 调用全部 6 个新方法，确认返回值类型正确
- [ ] 验证 `recall()` 返回 `list[RecallItem]`，字段 concept/activation/valence/detail_level/relative_time 均有值
- [ ] 验证 `recall_with_intuition()` 返回 `RecallResult`，含 `recall_items` 和 `intuition`
- [ ] 验证 `heartbeat_maintenance()` 执行 granular_decay + advance_lifecycle + process_cognitive_decay
- [ ] 验证 `derive_profile()` 返回 `ProfileView`，含 subject/observer/associations/voices
- [ ] 验证 `reflect()` 返回 `ReflectResult`，含 subject/agent_id/voices/contradictions
- [ ] 验证 `weave_narrative()` 返回 dict 含 fragment/episode/saga 统计

**验证**：6 个新 Protocol 方法全部可通过核心层调用，返回值类型与 design.md 一致

---

## 4. ThinkContext 扩展 + 直觉接入思考循环

**目标**：将直觉召回结果接入 ThinkContext，prompt_builder 可利用直觉信息构建提示词。

**覆盖差距**：G20（直觉召回未接入思考循环）、G12（ThinkContext.memory_snippets 填充规则不明确）

**批间依赖**：依赖第 3 批完成（recall_with_intuition Protocol 方法）

### 4.1 ThinkContext 扩展

- [ ] 在 `src/core/types.py` 的 `ThinkContext` 中新增 `intuition_context: IntuitionContext | None = None` 字段（在 `memory_snippets` 之后）
- [ ] 更新 `ThinkContext` 的文档注释，说明 `intuition_context` 的语义：直觉引擎的快速预判结果，供 prompt_builder 使用

**验证**：`ThinkContext(messages=(), intuition_context=IntuitionContext(...))` 可正常实例化；旧代码 `ThinkContext(messages=())` 不受影响

### 4.2 prompt_builder 集成直觉召回

- [ ] 在 `src/maisaka/agent_autonomy/prompt_builder.py` 中，记忆检索阶段改为优先调用 `recall_with_intuition()`（替代 `search()`），将返回的 `RecallResult` 拆分为 `memory_snippets` 和 `intuition_context`
- [ ] 在 prompt 构建逻辑中，当 `intuition_context` 非空时，将直觉触发结果（triggered_entries/triggered_episodes/triggered_sagas）格式化注入提示词
- [ ] 确保 `memory_snippets` 的填充规则统一：从 `RecallItem.concept` + `RecallItem.detail_level` 生成自然语言描述

**验证**：prompt_builder 构建的提示词包含直觉上下文；思考循环延迟不增加（直觉召回 ≤50ms）

### 4.3 agent.py 记忆检索路径迁移

- [ ] 在 `src/maisaka/agent_autonomy/agent.py` 中，将记忆检索从 `search()` 迁移为 `recall_with_intuition()`，填充 `ThinkContext.intuition_context`
- [ ] 确保 `AgentMemoryAdapter` 的 `search()` 方法仍可用（向后兼容），但新增 `recall_with_intuition()` 代理方法

**验证**：智能体思考时 ThinkContext 包含直觉上下文；旧路径 `search()` 不受影响

### 4.4 heuristic_injector 迁移

- [ ] 在 `src/maisaka/memory/heuristic_injector.py` 中，启发式注入改用直觉路径（`recall_with_intuition()`），替代 `search()` + 手动规则
- [ ] 保留 `search()` 作为降级路径（`TemporaryMemoryError` 时回退）

**验证**：启发式注入优先走直觉路径；直觉召回失败时降级到 search() 不崩溃

---

## 5. 心跳维护接入核心调度

**目标**：将 heartbeat_maintenance() 接入 main.py 的心跳调度，替代 maintain_memory(action="decay")。

**覆盖差距**：G25（心跳维护未接入核心调度）

**批间依赖**：依赖第 3 批完成（heartbeat_maintenance Protocol 方法）

### 5.1 心跳调度迁移

- [ ] 在 `src/main.py` 的心跳调度逻辑中，将 `memory_port.maintain_memory(action="decay")` 替换为 `memory_port.heartbeat_maintenance(agent_id="", elapsed_hours=...)`
- [ ] 保留 `maintain_memory()` 方法用于手动维护操作（WebUI/CLI），仅心跳调度切换到 `heartbeat_maintenance()`
- [ ] 在心跳调度处添加异常捕获：`TemporaryMemoryError` 跳过本次心跳，`PermanentMemoryError` 记录 error 日志

**验证**：心跳调度每次触发 granular_decay + advance_lifecycle + process_cognitive_decay；心跳单次执行 ≤2s

### 5.2 心跳结果监控

- [ ] 在心跳调度处记录 `heartbeat_maintenance()` 返回的 `elapsed_ms`，超过阈值（如 1500ms）时记录 warning 日志
- [ ] 确保 Fragment/Episode/Saga 生命周期正常推进（通过日志或 WebUI 验证）

**验证**：心跳日志包含 decay/lifecycle/cognitive_decay 三项结果；超时有 warning 日志

---

## 6. ingest_text 全链路删除 + 情绪联动

**目标**：彻底删除 ingest_text 全链路（三层 DeprecationWarning + host_service 分支 + 死代码），不留过渡期痕迹。实现情绪与记忆效价联动。

**覆盖差距**：G7（废弃方法残留）、G17（情绪与记忆效价未联动）

**批间依赖**：依赖第 2 批完成（observe_experience 签名变更后才能安全删除 ingest_text）

**CC 审查关键决策**：不要保留 DeprecationWarning 过渡期。三层全删：Protocol 签名、适配器实现、中间层方法、host_service 分支、migration_ingest_text 死代码、mem_write 加的 warning 一并清理。

### 6.1 ingest_text 全链路彻底删除

- [ ] 在 `src/core/protocols.py` 中移除 `ingest_text()` 方法定义
- [ ] 在 `src/core/adapters/memory_service.py` 中移除 `ingest_text()` 方法实现（含 mem_write 加的 DeprecationWarning）
- [ ] 在 `src/services/memory_service.py` 中移除 `ingest_text()` 和 `migration_ingest_text()` 方法（含 DeprecationWarning）
- [ ] 在 `src/A_memorix/host_service.py` 中移除 `"ingest_text"` 分支（line 262-265）和 `"migration_ingest_text"` 分支（line 500-506）
- [ ] 在 `src/A_memorix/host_service.py` 的超时组件列表中移除 `"ingest_text"` 和 `"migration_ingest_text"`
- [ ] 确认所有外部调用方已迁移：`rg "ingest_text" src/` 仅剩 A_memorix 内部服务（ingest.py/fuzzy_modify.py/feedback_correction.py）和文档（README/QUICK_START/CHANGELOG），这些是 A_memorix 内部实现，不在本期删除范围

**验证**：Protocol 从 10 方法变为 9 方法 + 6 新方法 = 15 方法；核心层和中间层无 ingest_text 痕迹

### 6.2 情绪与记忆效价联动

- [ ] 在 `src/maisaka/agent_autonomy/experience_writer.py` 中，`_emotion_to_valence()` 方法改为从 `EmotionManager` 实时情绪自动推导 valence，而非从 `ThinkResult.emotion_type` 手动映射
- [ ] 新增 `EmotionManager` 注入：`ExperienceWriter.__init__()` 接受可选的 `emotion_manager` 参数
- [ ] 在 `write_experience()` 中，当 `emotion_manager` 可用时，从 `emotion_manager.get_current_state()` 获取实时情绪，推导 valence
- [ ] 保留 `_emotion_to_valence()` 作为降级路径（emotion_manager 不可用时）

**验证**：智能体当前情绪为"愤怒"时，observe_experience() 的 valence 自动为"negative"；emotion_manager 不可用时降级到 ThinkResult.emotion_type 映射

---

## 风险点与注意事项

### 风险 1：异常上浮导致现有功能异常中断

- **概率**：高 | **影响**：高
- **缓解**：第 1 批一次性移除所有 try-except，调用方崩溃了就修调用方。早暴露早修复，不让它们继续躲在兜底后面
- **唯一的例外**：如果崩溃导致容器无法启动——此时可以临时 catch 但必须加 ERROR 日志 + 倒计时移除

### 风险 2：数据类型下放 common 层导致循环导入

- **概率**：低 | **影响**：高
- **缓解**：common 层只放纯数据类（dataclass/frozen=True），不放业务逻辑。Protocol 留在 core，不在 common
- **回滚**：恢复 core/types.py 原始定义，common 层改为重新导出

### 风险 3：observe_experience() 签名变更导致调用方崩溃

- **概率**：中 | **影响**：中（仅 experience_writer 一处直接调用）
- **缓解**：ObserveRequest 所有字段有默认值，现有调用方可逐步迁移
- **回滚**：恢复关键字参数签名，ObserveRequest 保留但标记为实验性

### 风险 4：心跳维护接入后性能不达标

- **概率**：低 | **影响**：中
- **缓解**：heartbeat_maintenance() 已有性能日志（elapsed_ms），可监控。如超时可拆分为三次独立调用
- **回滚**：心跳调度恢复为 maintain_memory(action="decay")

### 风险 5：ingest_text 删除后 A_memorix 内部服务断裂

- **概率**：低 | **影响**：中
- **缓解**：A_memorix 内部的 ingest.py/fuzzy_modify.py/feedback_correction.py 仍使用 kernel.ingest_text()，这是 A_memorix 内部路径，不走 Protocol。本期只删除 Protocol→适配器→中间层→host_service 分支的链路，不动 A_memorix 内部服务

### 注意事项

1. **组件兼容核心原则**：核心层新增代码禁止引入对 chat_manager、send_service、HeartFlow 等组件具体实现的直接导入
2. **禁止核心导入 A_memorix 内部模块**：适配器层是唯一允许同时导入核心 Protocol 和 A_memorix 具体类的地方
3. **不兜底原则**：适配器层和中间层不吞没异常，让错误完整上浮
4. **配置文件修改**：只改模板 + 版本号，不改动 legacy_migration
5. **提示词修改**：需三语同步（zh-CN / en-US / ja-JP）
6. **提交归属标记**：commit message 末尾加 [CA]/[CC]/[WB]/[MC]
7. **Protocol 新增方法不破坏现有实现**：Python Protocol 的鸭子类型特性保证新增方法不影响已有实现类
8. **单例化需提供 reset_for_test()**：全局单例让单元测试不可 mock，必须提供重置函数
9. **不回滚只前滚**：异常上浮后如果调用方崩溃，修调用方，不恢复 try-except

---

## 差距覆盖矩阵

| 差距 | 批次 | 任务编号 |
|------|------|---------|
| G1 缺失直觉召回接口 | 第 3 批 | 3.1, 3.2, 3.3, 3.4 |
| G2 缺失连接主义召回接口 | 第 3 批 | 3.1, 3.2, 3.3, 3.4 |
| G3 缺失画像实时视图接口 | 第 3 批 | 3.1, 3.2, 3.3, 3.4 |
| G4 缺失心跳维护接口 | 第 3 批 | 3.1, 3.2, 3.3, 3.4 |
| G5 缺失叙事编织接口 | 第 3 批 | 3.1, 3.2, 3.3, 3.4 |
| G6 缺失反思接口 | 第 3 批 | 3.1, 3.2, 3.3, 3.4 |
| G7 废弃方法残留 | 第 6 批 | 6.1 |
| G8 search() 参数语义偏移 | 第 2 批 | 2.7 |
| G9 ObserveRequest 与 observe_experience() 不对齐 | 第 2 批 | 2.6 |
| G10 MemoryWriteResult 与 ObserveResult 不对齐 | 第 2 批 | 2.1 |
| G11 MemorySearchResult 与 RecallItem 不对齐 | 第 2 批 | 2.1 |
| G12 ThinkContext.memory_snippets 填充规则不明确 | 第 4 批 | 4.2 |
| G13 适配器实例重复创建 | 第 1 批 | 1.2, 1.3 |
| G14 适配器层延迟导入 memory_service | 第 1 批 | 1.2 |
| G15 A_memorix/core/ 反向依赖核心层 | 第 2 批 | 2.4, 2.5 |
| G16 host_service 直接访问 kernel 私有属性 | — | 不在本期范围 |
| G17 情绪与记忆效价未联动 | 第 6 批 | 6.2 |
| G18 Agent-owns-Thinking 与记忆性格未联动 | 第 3 批 | 3.1（agent_id 参数传递） |
| G19 管家系统与记忆系统未联动 | — | 不在本期范围 |
| G20 直觉召回未接入思考循环 | 第 4 批 | 4.1-4.4 |
| G21 叙事弧未接入智能体认知 | 第 3 批 | 3.1（weave_narrative 暴露） |
| G22 AsyncWriteQueue 延迟启动竞态 | — | 不在本期范围 |
| G23 ModelConfigPort 注入时序无检查 | — | 不在本期范围 |
| G24 记忆性格注册窗口期 | — | 不在本期范围 |
| G25 心跳维护未接入核心调度 | 第 5 批 | 5.1, 5.2 |
| G26 适配器层全面吞没异常 | 第 1 批 | 1.4, 1.5, 1.6 |
| G27 get_person_profile() 返回 None 语义模糊 | 第 1 批 + 第 2 批 | 1.4, 2.8 |
| G28 A_memorix 内部 bare except | — | 不在本期范围 |
| G29 memory_service 中间层双重兜底 | 第 1 批 | 1.5 |

**本期覆盖**：25/29 项差距（G16/G19/G22-G24/G28 不在本期范围，已标注原因）
