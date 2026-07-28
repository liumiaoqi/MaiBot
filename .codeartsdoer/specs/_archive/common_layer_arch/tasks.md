# SSD-9：Common 层架构归正 — 编码任务规划

## 迁移概览

| 批次 | 主题 | 负责人 | 任务数 |
|------|------|--------|--------|
| 1 | H6 参数注入（utils_message.py 签名修改 + 6 调用方适配 + ruff 守卫验证） | Codex | 8 |
| 2 | M8 Protocol + 适配器（PersonInfoPort + PersonInfoResult + 注册点 + 适配器 + message_utils.py 迁移 + 启动注册 + ruff 守卫） | CC | 8 |

**反向依赖消除总计**：H6 消除 1 处 common→chat 函数内导入 + M8 消除 1 处 core→person_info 直接导入

**文件锁规则**：同一批次内文件互不重叠；跨批次文件锁在任务描述中标注。

---

## 1. H6 参数注入（utils_message.py 签名修改 + 6 调用方适配）

**负责人**：Codex（参数注入，定义清晰，机械性替换）

**前置条件**：无

**关键约束**：
- `store_message_to_db` 是同步方法（在 `_DB_WRITE_THREAD_LOCK` 内执行），不能改为异步
- `ChatRuntimeRegistry.get_runtime()` 是异步方法，无法在同步上下文中直接调用
- 解决方案：调用方在异步上下文中预先获取运行时信息，构造同步 provider 闭包传递
- `universal_message_sender.py` 和 `uni_message_sender.py` 在同步 `with get_db_session()` 块内调用 `fill_reply_frequency_if_available`，需在进入同步块之前预获取运行时

### 1.1 修改 utils_message.py 签名 + 删除反向依赖

- [ ] 修改 `src/common/utils/utils_message.py`，消除对 `heartflow_manager` 的函数内导入：
  - **新增类型别名**（在模块顶层，约 L44 附近）：
    ```python
    from typing import Callable, Optional
    ReplyFrequencyProvider = Callable[[], Optional[float]]
    ```
  - **修改 `fill_reply_frequency_if_available` 签名**（L235）：
    ```python
    @staticmethod
    def fill_reply_frequency_if_available(
        message: "SessionMessage",
        reply_frequency_provider: ReplyFrequencyProvider | None = None,
    ) -> None:
    ```
  - **修改方法体**：
    1. 删除函数内 `from src.chat.heart_flow.heartflow_manager import heartflow_manager`（L246）
    2. 删除 `runtime = heartflow_manager.heartflow_chat_list.get(session_id)` 及后续的 `runtime._get_effective_reply_frequency()` 调用（L248-251）
    3. 新增 provider 优先逻辑：
       ```python
       if reply_frequency_provider is not None:
           try:
                freq = reply_frequency_provider()
               if freq is not None:
                   message.reply_frequency = freq
                   return
           except Exception as exc:
               logger.debug(f"通过 provider 补充消息回复频率失败: session_id={session_id} error={exc}")
       ```
    4. 保留 `ChatConfigUtils.get_talk_value` 降级分支（L253-256），作为 provider 未提供或返回 None 时的降级路径
  - **修改 `store_message_to_db` 签名**（L210）：
    ```python
    @staticmethod
    def store_message_to_db(
        message: "SessionMessage",
        reply_frequency_provider: ReplyFrequencyProvider | None = None,
    ):
    ```
  - **修改 `store_message_to_db` 方法体**（L220）：
    ```python
    MessageUtils.fill_reply_frequency_if_available(message, reply_frequency_provider)
    ```
  - **修改 `store_message_to_db_async` 签名**（L226）：
    ```python
    @staticmethod
    async def store_message_to_db_async(
        message: "SessionMessage",
        reply_frequency_provider: ReplyFrequencyProvider | None = None,
    ) -> None:
    ```
  - **修改 `store_message_to_db_async` 方法体**（L232）：
    ```python
    await asyncio.to_thread(MessageUtils.store_message_to_db, message, reply_frequency_provider)
    ```
  - **验收标准**：`rg "from src.chat" src/common/utils/utils_message.py` 零结果；`rg "heartflow_manager" src/common/utils/utils_message.py` 零结果；`fill_reply_frequency_if_available(message)` 不带 provider 参数时降级使用 `ChatConfigUtils.get_talk_value`，行为与当前降级路径一致
  - **文件锁**：`src/common/utils/utils_message.py`

### 1.2 send_service.py 调用方适配

- [ ] 修改 `src/services/send_service.py`（L613-619），构造 provider 并传递给 `store_message_to_db_async`：
  - 在 `_store_sent_message` 函数中：
    - 新增 `from src.core.runtime_port_registry import get_chat_runtime_registry`
    - 新增 `from src.common.utils.utils_config import ChatConfigUtils`
    - 在调用 `store_message_to_db_async` 之前，构造 provider：
      ```python
      async def _store_sent_message(message: SessionMessage) -> None:
          provider = await _build_reply_frequency_provider(message.session_id)
          await MessageUtils.store_message_to_db_async(message, reply_frequency_provider=provider)
      ```
    - 新增辅助函数（在 `_store_sent_message` 之前或之后）：
      ```python
      async def _build_reply_frequency_provider(session_id: str) -> ReplyFrequencyProvider | None:
          """在异步上下文中预先获取运行时信息，构造同步 provider 闭包。"""
          from src.core.runtime_port_registry import get_chat_runtime_registry
          from src.common.utils.utils_config import ChatConfigUtils
          from src.common.utils.utils_message import ReplyFrequencyProvider

          registry = get_chat_runtime_registry()
          runtime = await registry.get_runtime(session_id) if registry else None

          def _provider() -> float | None:
              if runtime is not None:
                  adjust = runtime.get_talk_frequency_adjust()
                  if adjust <= 0:
                      return 0.0
                  talk_value = float(ChatConfigUtils.get_talk_value(session_id))
                  return max(0.0, talk_value * adjust)
              return None

          return _provider
      ```
  - **验收标准**：`rg "store_message_to_db_async" src/services/send_service.py` 显示调用传递了 `reply_frequency_provider` 参数；消息入库时回复频率通过 provider 获取
  - **文件锁**：`src/services/send_service.py`

### 1.3 heartflow_message_processor.py 调用方适配

- [ ] 修改 `src/chat/heart_flow/heartflow_message_processor.py`（L60），构造 provider 并传递给 `store_message_to_db_async`：
  - 在调用 `store_message_to_db_async` 之前，构造 provider：
    ```python
    # 在 L56 获取 chat 之后、L60 之前
    from src.core.runtime_port_registry import get_chat_runtime_registry
    from src.common.utils.utils_config import ChatConfigUtils

    registry = get_chat_runtime_registry()
    runtime = await registry.get_runtime(message.session_id) if registry else None

    def _reply_freq_provider() -> float | None:
        if runtime is not None:
            adjust = runtime.get_talk_frequency_adjust()
            if adjust <= 0:
                return 0.0
            talk_value = float(ChatConfigUtils.get_talk_value(message.session_id))
            return max(0.0, talk_value * adjust)
        return None

    await MessageUtils.store_message_to_db_async(message, reply_frequency_provider=_reply_freq_provider)
    ```
  - 注意：此文件已有 `heartflow_manager` 导入（L1 附近），但不在本任务范围内清理——仅消除 `store_message_to_db_async` 调用点的反向依赖传递
  - **验收标准**：`rg "store_message_to_db_async" src/chat/heart_flow/heartflow_message_processor.py` 显示调用传递了 `reply_frequency_provider` 参数
  - **文件锁**：`src/chat/heart_flow/heartflow_message_processor.py`

### 1.4 bot.py 调用方适配

- [ ] 修改 `src/chat/message_receive/bot.py`（L362），构造 provider 并传递给 `store_message_to_db_async`：
  - 在 `_store_intercepted_command_message` 静态方法中：
    ```python
    @staticmethod
    async def _store_intercepted_command_message(message: SessionMessage) -> None:
        from src.core.runtime_port_registry import get_chat_runtime_registry
        from src.common.utils.utils_config import ChatConfigUtils

        registry = get_chat_runtime_registry()
        runtime = await registry.get_runtime(message.session_id) if registry else None

        def _reply_freq_provider(sid: str) -> float | None:
            if runtime is not None:
                adjust = runtime.get_talk_frequency_adjust()
                if adjust <= 0:
                    return 0.0
                talk_value = float(ChatConfigUtils.get_talk_value(sid))
                return max(0.0, talk_value * adjust)
            return None

        await MessageUtils.store_message_to_db_async(message, reply_frequency_provider=_reply_freq_provider)
    ```
  - **验收标准**：`rg "store_message_to_db_async" src/chat/message_receive/bot.py` 显示调用传递了 `reply_frequency_provider` 参数
  - **文件锁**：`src/chat/message_receive/bot.py`

### 1.5 message_gateway.py 调用方适配

- [ ] 修改 `src/plugin_runtime/host/message_gateway.py`（L110-113），构造 provider 并传递给 `store_message_to_db_async`：
  - 在 `try` 块内，`store_message_to_db_async` 调用之前，构造 provider：
    ```python
    from src.core.runtime_port_registry import get_chat_runtime_registry
    from src.common.utils.utils_config import ChatConfigUtils

    registry = get_chat_runtime_registry()
    runtime = await registry.get_runtime(internal_message.session_id) if registry else None

    def _reply_freq_provider() -> float | None:
        if runtime is not None:
            adjust = runtime.get_talk_frequency_adjust()
            if adjust <= 0:
                return 0.0
            talk_value = float(ChatConfigUtils.get_talk_value(message.session_id))
            return max(0.0, talk_value * adjust)
        return None

    await MessageUtils.store_message_to_db_async(internal_message, reply_frequency_provider=_reply_freq_provider)
    ```
  - **验收标准**：`rg "store_message_to_db_async" src/plugin_runtime/host/message_gateway.py` 显示调用传递了 `reply_frequency_provider` 参数
  - **文件锁**：`src/plugin_runtime/host/message_gateway.py`

### 1.6 universal_message_sender.py 调用方适配

- [ ] 修改 `src/common/message_server/universal_message_sender.py`（L66-70），构造 provider 并传递给 `fill_reply_frequency_if_available`：
  - **关键注意**：此处在同步 `with get_db_session()` 块内调用 `fill_reply_frequency_if_available`，需要在进入同步块之前预获取运行时
  - 在 `send_message` 方法中，`if storage_message:` 块之前（约 L65），预获取运行时：
    ```python
    # 预获取运行时信息（在同步块之前）
    from src.core.runtime_port_registry import get_chat_runtime_registry
    from src.common.utils.utils_config import ChatConfigUtils

    registry = get_chat_runtime_registry()
    runtime = await registry.get_runtime(message.session_id) if registry else None

    def _reply_freq_provider() -> float | None:
        if runtime is not None:
            adjust = runtime.get_talk_frequency_adjust()
            if adjust <= 0:
                return 0.0
            talk_value = float(ChatConfigUtils.get_talk_value(message.session_id))
            return max(0.0, talk_value * adjust)
        return None
    ```
  - 修改 `fill_reply_frequency_if_available` 调用（L69）：
    ```python
    MessageUtils.fill_reply_frequency_if_available(message, reply_frequency_provider=_reply_freq_provider)
    ```
  - **验收标准**：`rg "fill_reply_frequency_if_available" src/common/message_server/universal_message_sender.py` 显示调用传递了 `reply_frequency_provider` 参数
  - **文件锁**：`src/common/message_server/universal_message_sender.py`

### 1.7 uni_message_sender.py 调用方适配

- [ ] 修改 `src/chat/message_receive/uni_message_sender.py`（L374-377），构造 provider 并传递给 `fill_reply_frequency_if_available`：
  - **关键注意**：与 1.6 相同，此处也在同步 `with get_db_session()` 块内调用，需在进入同步块之前预获取运行时
  - 在 `if storage_message:` 块之前（约 L373），预获取运行时：
    ```python
    # 预获取运行时信息（在同步块之前）
    from src.core.runtime_port_registry import get_chat_runtime_registry
    from src.common.utils.utils_config import ChatConfigUtils

    registry = get_chat_runtime_registry()
    runtime = await registry.get_runtime(message.session_id) if registry else None

    def _reply_freq_provider() -> float | None:
        if runtime is not None:
            adjust = runtime.get_talk_frequency_adjust()
            if adjust <= 0:
                return 0.0
            talk_value = float(ChatConfigUtils.get_talk_value(message.session_id))
            return max(0.0, talk_value * adjust)
        return None
    ```
  - 修改 `fill_reply_frequency_if_available` 调用（L376）：
    ```python
    MessageUtils.fill_reply_frequency_if_available(message, reply_frequency_provider=_reply_freq_provider)
    ```
  - **验收标准**：`rg "fill_reply_frequency_if_available" src/chat/message_receive/uni_message_sender.py` 显示调用传递了 `reply_frequency_provider` 参数
  - **文件锁**：`src/chat/message_receive/uni_message_sender.py`

### 1.8 H6 全量验证

- [ ] 执行全量验证，确认 H6 反向依赖消除完成：
  - 运行 `rg "from src.chat" src/common/` → 零结果（common 层零 chat 层导入）
  - 运行 `rg "from src.core" src/common/` → 零结果（common 层零 core 层导入）
  - 运行 `rg "heartflow_manager" src/common/utils/utils_message.py` → 零结果
  - 运行 `rg "heartflow_manager.heartflow_chat_list" src/` → 零结果（确认没有其他地方用同样的方式访问）
  - 确认 `fill_reply_frequency_if_available(message)` 不带 provider 参数时降级行为与当前一致
  - 确认 `store_message_to_db_async(message)` 不带 provider 参数时降级行为与当前一致
  - **验收标准**：5 条验证命令结果符合预期；降级行为正确
  - **文件锁**：无（验证任务，不修改文件）

---

## 2. M8 Protocol + 适配器（PersonInfoPort + 注册点 + message_utils.py 迁移 + 启动注册 + ruff 守卫）

**负责人**：CC（Protocol 设计需理解为什么，注册点模式需与已有模式一致，message_utils.py 迁移需理解 Person 类依赖链）

**前置条件**：无（与批次 1 独立，可并行）

### 2.1 新增 PersonInfoPort Protocol

- [ ] 在 `src/core/protocols.py` 中新增 `PersonInfoPort` Protocol 定义：
  - 在 `MessageIngestionPort` 之后（约 L199 之后）新增：
    ```python
    @runtime_checkable
    class PersonInfoPort(Protocol):
        """人物信息查询接口 — 核心通过此接口查询人物信息，不直接依赖 Person 类。"""

        def get_person_info(self, platform: str, user_id: str) -> Optional["PersonInfoResult"]:
            """查询人物信息。

            Args:
                platform: 平台标识
                user_id: 用户 ID

            Returns:
                PersonInfoResult 查询结果，不存在时返回 None
            """
    ```
  - 在 `TYPE_CHECKING` 块中新增 `PersonInfoResult` 的导入（从 `src.core.types` 导入）
  - **验收标准**：`PersonInfoPort` Protocol 定义完整，方法签名与 design.md 2.2.2 一致；`isinstance(adapter_instance, PersonInfoPort)` 返回 True（鸭子类型兼容）
  - **文件锁**：`src/core/protocols.py`

### 2.2 新增 PersonInfoResult 数据类

- [ ] 在 `src/core/types.py` 中新增 `PersonInfoResult` 数据类：
  - 在文件适当位置（建议在 `MemorySearchResult` 等数据类附近）新增：
    ```python
    @dataclass(frozen=True)
    class PersonInfoResult:
        """人物信息查询结果 — 不可变数据对象。"""

        is_known: bool
        person_id: Optional[str] = None
        person_name: Optional[str] = None
    ```
  - 确保文件中已有 `from dataclasses import dataclass` 和 `from typing import Optional` 导入
  - **验收标准**：`PersonInfoResult(is_known=True, person_id="123", person_name="test")` 可正常创建；`PersonInfoResult(is_known=True).person_id` 为 None；尝试修改属性抛出 `FrozenInstanceError`
  - **文件锁**：`src/core/types.py`

### 2.3 新增 person_info_port_registry.py 注册点

- [ ] 新建 `src/core/person_info_port_registry.py`，实现 PersonInfoPort 注册点：
  - 遵循项目已有的注册点模式（与 `runtime_port_registry.py`、`message_ingestion_port.py` 一致）：
    ```python
    """人物信息端口全局注册点 — 核心通过此注册点查询人物信息，不直接依赖 Person 类。"""

    from __future__ import annotations

    from typing import Optional

    from src.core.protocols import PersonInfoPort
    from src.common.logger import get_logger

    logger = get_logger("core.person_info_port_registry")

    _provider: Optional[PersonInfoPort] = None


    def get_person_info_port() -> Optional[PersonInfoPort]:
        """获取全局 PersonInfoPort 实例。

        Returns:
            PersonInfoPort 实例，未注册时返回 None
        """
        return _provider


    def set_person_info_port(port: PersonInfoPort) -> None:
        """注册全局 PersonInfoPort 实例。"""
        global _provider
        if _provider is not None:
            logger.warning("PersonInfoPort 已注册，将被覆盖")
        _provider = port


    def reset_person_info_port() -> None:
        """重置 PersonInfoPort 实例（测试用）。"""
        global _provider
        _provider = None
    ```
  - **验收标准**：`get_person_info_port()` 未注册时返回 None；`set_person_info_port(adapter)` 后 `get_person_info_port()` 返回 adapter；`reset_person_info_port()` 后返回 None
  - **文件锁**：`src/core/person_info_port_registry.py`

### 2.4 新增 PersonInfoPortAdapter 适配器

- [ ] 新建 `src/core/adapters/person_info_port.py`，实现 PersonInfoPort 适配器：
  - 遵循项目已有的适配器模式（与 `message_ingestion_port.py` 一致，鸭子类型包裹）：
    ```python
    """PersonInfoPort 适配器 — 委托 Person 类完成查询，核心层无感知。"""

    from __future__ import annotations

    from typing import Optional

    from src.common.logger import get_logger

    logger = get_logger("core.adapters.person_info_port")

    class PersonInfoPortAdapter:
        """PersonInfoPort 适配器 — 委托 Person 类完成查询。"""

        def get_person_info(self, platform: str, user_id: str) -> Optional["PersonInfoResult"]:
            """查询人物信息，委托 Person 类完成。"""
            try:
                from src.person_info.person_info import Person
                from src.core.types import PersonInfoResult

                person = Person(platform=platform, user_id=user_id)
                if not person.is_known:
                    return PersonInfoResult(is_known=False)
                return PersonInfoResult(
                    is_known=True,
                    person_id=person.person_id,
                    person_name=person.person_name,
                )
            except Exception as exc:
                logger.warning(f"查询人物信息失败: platform={platform} user_id={user_id} error={exc}")
                return None
    ```
  - **验收标准**：`isinstance(PersonInfoPortAdapter(), PersonInfoPort)` 返回 True（鸭子类型兼容）；`get_person_info` 返回 `PersonInfoResult` 或 None；Person 类异常时返回 None 而非抛出
  - **文件锁**：`src/core/adapters/person_info_port.py`

### 2.5 修改 message_utils.py 使用 PersonInfoPort

- [ ] 修改 `src/core/message_utils.py`，消除对 `Person` 类的直接导入：
  - **删除导入**（L26）：`from src.person_info.person_info import Person`
  - **新增导入**：
    ```python
    from src.core.person_info_port_registry import get_person_info_port
    from src.core.types import PersonInfoResult
    ```
  - **修改 `get_chat_type_and_target_info` 方法体**（L265-279）：
    将 Person 类直接使用改为通过 PersonInfoPort 查询：
    ```python
    # 替换原 L266-279 的 Person 使用
    try:
        port = get_person_info_port()
        if port is None:
            logger.warning("PersonInfoPort 未注册，无法查询人物信息")
            return False, None
        person_result = port.get_person_info(platform, user_id)
        if person_result is None or not person_result.is_known:
            logger.warning(f"用户 {user_nickname} 尚未认识")
            return False, None
        target_info.is_known = True
        if person_result.person_id:
            target_info.person_id = person_result.person_id
            target_info.person_name = person_result.person_name
    except Exception as person_e:
        logger.warning(
            f"获取 person_id 或 person_name 时出错 for {platform}:{user_id} in utils: {person_e}"
        )
    ```
  - **验收标准**：`rg "from src.person_info" src/core/message_utils.py` 零结果；`get_chat_type_and_target_info` 通过 PersonInfoPort 查询人物信息；PersonInfoPort 未注册时降级返回 `(False, None)`
  - **文件锁**：`src/core/message_utils.py`

### 2.6 启动注册 PersonInfoPortAdapter

- [ ] 修改 `src/main.py`，在启动流程中注册 PersonInfoPortAdapter：
  - **新增启动步骤**：在 `CORE_SERVICES` 阶段，`_init_message_ingestion_port`（order=8）之后新增 `_init_person_info_port`（order=9），后续步骤顺延：
    ```python
    orchestrator.register(StartupComponent(
        name="person_info_port", phase=StartupPhase.CORE_SERVICES, order=9, critical=True,
        init_fn=self._init_person_info_port,
    ))
    ```
  - **新增静态方法**：
    ```python
    @staticmethod
    async def _init_person_info_port() -> None:
        from src.core.adapters.person_info_port import PersonInfoPortAdapter
        from src.core.person_info_port_registry import set_person_info_port
        set_person_info_port(PersonInfoPortAdapter())
    ```
  - 注意：原 order=9 的 `prompt_manager` 需顺延为 order=10
  - **验收标准**：启动后 `get_person_info_port()` 返回 `PersonInfoPortAdapter` 实例；`isinstance(get_person_info_port(), PersonInfoPort)` 返回 True
  - **文件锁**：`src/main.py`

### 2.7 适配器 __init__.py 导出更新 + ruff 守卫 + per-file-ignores

- [ ] 修改 3 个配置/导出文件：
  - **`src/core/adapters/__init__.py`**：新增 PersonInfoPort 相关导出
    - 新增 `from src.core.adapters.person_info_port import PersonInfoPortAdapter  # noqa: F401`
    - 新增 `from src.core.person_info_port_registry import get_person_info_port, reset_person_info_port  # noqa: F401`
    - 在 `__all__` 列表中新增 `"PersonInfoPortAdapter"`、`"get_person_info_port"`、`"reset_person_info_port"`
    - ⚠️ **历史重犯提醒**：SSD-6/SSD-7/SSD-8 各忘更新 `__all__` 一次，务必自检！
  - **`pyproject.toml`**：
    - 在 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 中新增：
      ```toml
      "src.person_info.person_info.Person" = {msg = "core 层禁止直接导入 Person 类，请使用 PersonInfoPort Protocol 接口（get_person_info_port()）"}
      ```
    - 在 `[tool.ruff.lint.per-file-ignores]` 中确认 `src/core/adapters/*` 已有 `["TID251"]` 通配规则（L110），无需新增 `person_info_port.py` 的单独条目
  - **验收标准**：`from src.core.adapters import get_person_info_port` 可正常导入；在 `src/core/message_utils.py` 中添加 `from src.person_info.person_info import Person` → ruff check 报 TID251 错误；适配器层 `person_info_port.py` 不触发 TID251
  - **文件锁**：`src/core/adapters/__init__.py`、`pyproject.toml`

### 2.8 M8 全量验证

- [ ] 执行全量验证，确认 M8 反向依赖消除完成：
  - 运行 `rg "from src.person_info" src/core/` → 零结果（core 层零 person_info 导入）
  - 运行 `rg "Person" src/core/message_utils.py` → 仅剩注释或 `PersonInfoResult`/`PersonInfoPort` 相关引用，无 `from src.person_info.person_info import Person`
  - 运行 `ruff check src/core/` → 零 TID251 违规（除已豁免文件外）
  - 确认 `PersonInfoPortAdapter` 满足 `PersonInfoPort` Protocol（`isinstance(adapter, PersonInfoPort)` 返回 True）
  - 确认 `get_chat_type_and_target_info` 在 PersonInfoPort 未注册时降级返回 `(False, None)`
  - 确认 `get_chat_type_and_target_info` 在 PersonInfoPort 已注册时正常返回人物信息
  - **验收标准**：6 条验证命令结果符合预期；Protocol 鸭子类型检查通过；降级行为正确
  - **文件锁**：无（验证任务，不修改文件）

### 2.9 AGENTS.md 更新

- [ ] 修改 `AGENTS.md`，更新核心接口层表格和架构债务追踪：
  - **核心接口层表格**：新增 `PersonInfoPort` 行（职责：人物信息查询，实现者：PersonInfoPortAdapter，状态：✅ 已实现）
  - **SSD-9 进展章节**：新增"Common层架构归正进展（SSD-9，已完成）"章节，包含迁移架构、已完成批次、消除的架构债务、待后续事项
  - **核心禁止项**：无需新增（common→chat 和 core→person_info 反向依赖不属于核心禁止项，而是层级依赖约束）
  - **验收标准**：AGENTS.md 中 PersonInfoPort 行存在且信息正确；SSD-9 章节完整
  - **文件锁**：`AGENTS.md`

---

## 附录：不在范围内的事项

1. **fill_reply_frequency_if_available 业务逻辑重构**：不改变回复频率的计算规则，只改变获取方式
2. **get_chat_type_and_target_info 业务逻辑重构**：不改变查询逻辑，只改变获取人物信息的方式
3. **person_info 模块本身的位置或架构迁移**：person_info 仍作为独立模块存在
4. **person_info 被其他模块导入的情况**：services/chat/maisaka/plugin_runtime 等上层模块导入 person_info 是合法的
5. **maisaka/runtime.py 和 maisaka/turn_scheduler.py 对 _get_effective_reply_frequency 的调用**：同层调用，合法
6. **heartflow_message_processor.py 中其他 heartflow_manager 导入**：仅消除 store_message_to_db_async 调用点的反向依赖传递
7. **ChatConfigUtils.get_talk_value 降级逻辑**：保留原样，不修改
8. **_get_effective_reply_frequency 私有方法暴露**：不修改 ChatRuntime Protocol，调用方通过 `get_talk_frequency_adjust()` + `ChatConfigUtils.get_talk_value()` 组合计算