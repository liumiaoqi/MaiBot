# 三角色切分规范

> 来源：Cordis 三角色哲学 + MaiBot 微内核架构实践。
> 定位：插件开发规范——指导插件开发者按三角色组织代码。
> 关联机制：Port/Protocol（`src/core/protocols.py`）、适配器层（`src/core/adapters/`）、scope（ZG16-5）、depends_on（ZG16-3）。

---

## 一、三角色定义

MaiBot 微内核架构遵循三角色切分哲学：**Service Definition / Provider / Consumer**。

| 角色 | 职责 | 代码位置 | 例子 |
|------|------|---------|------|
| **Service Definition**（服务声明） | 声明能力接口——Protocol/Port | `src/core/protocols.py` | `AppConfigPort`、`MemoryServicePort`、`ErrorEscalationPort` |
| **Provider**（服务实现） | 实现接口——适配器层 | `src/core/adapters/` | `GlobalConfigAppConfigPort`、`MemoryServiceAdapter` |
| **Consumer**（服务消费） | 使用能力——业务模块 | `src/maisaka/`、`src/chat/` 等 | `chat_loop_service.py`、`post_processor.py` |

### 核心思想

**换 Provider = 换整个能力，Consumer 不感知。**

```
Consumer（业务模块）
    ↓ 依赖 Protocol 接口（不依赖具体实现）
Service Definition（Protocol/Port）
    ↑ 实现注入（main.py 启动时 set_*()）
Provider（适配器）
```

- Consumer 只导入 Protocol（`from src.core.protocols import AppConfigPort`），不导入适配器具体类
- Provider 在 `main.py` 启动时通过 `set_app_config_port(GlobalConfigAppConfigPort())` 注入
- 换 Provider（如测试时换 MockProvider）只需改注入点，Consumer 代码不变

### 现有 Port/Protocol 清单

| Port | Protocol 定义 | 适配器实现 | 消费方 |
|------|-------------|-----------|--------|
| AppConfigPort | `protocols.py:1157` | `adapters/app_config_port.py` | 全局配置读取 |
| MemoryServicePort | `protocols.py:349` | `adapters/memory_service.py` | A_memorix 记忆服务 |
| ErrorEscalationPort | `protocols.py` | `adapters/` + `error_escalation_port_registry.py` | 错误上报 |
| ChatConfigPort | `protocols.py` | `adapters/chat_config_port.py` | 聊天配置 |
| LLMServicePort | `protocols.py` | `adapters/llm_service_port.py` | LLM 调用 |
| MessagePort | `protocols.py` | `adapters/message_port_v2.py` | 消息收发 |

---

## 二、插件开发者指引

### 2.1 声明什么（Service Definition 侧）

插件通过 `_manifest.json` 声明能力需求：

```json
{
    "manifest_version": 3,
    "id": "org.example.my_plugin",
    "scopes": [
        "message:send:text",
        "database:read:self",
        "llm:execute:generate"
    ],
    "dependencies": ["org.example.other_plugin"]
}
```

- **scopes**：声明所需权限（ZG16-5 词汇表 `src/plugin_runtime_v2/scope/vocabulary.py`）
- **dependencies**：声明插件依赖（ZG16-3 depends_on 拓扑）

### 2.2 实现放哪（Provider 侧）

插件代码组织：

```
plugins/my_plugin/
    plugin.py          # 插件入口（MaiBotPlugin 子类）
    _manifest.json     # 能力声明
    config.py          # 插件配置模型（pydantic）
    tools.py           # @Tool 装饰器注册的工具
    commands.py        # @Command 装饰器注册的命令
    hooks.py           # @HookHandler 装饰器注册的钩子
```

- **@Tool**：声明拉取式组件（LLM 工具循环中调用）
- **@Command**：声明推送式组件（用户命令触发）
- **@HookHandler**：声明生命周期钩子（启动/停止/消息接收）
- **@EventHandler**：声明事件处理器

插件通过 `PluginContext` 获取能力（不直接导入核心模块）：

```python
class MyPlugin(MaiBotPlugin):
    scopes = ["message:send:text", "database:read:self"]

    async def on_load(self, ctx: PluginContext) -> None:
        # ctx.send → 消息发送能力（message:send:* scope）
        # ctx.storage → 键值存储能力（database:read/write:self scope）
        # ctx.llm → LLM 调用能力（llm:execute:* scope）
        pass
```

### 2.3 怎么被消费（Consumer 侧）

插件被消费的方式：

| 消费方 | 消费方式 | 例子 |
|--------|---------|------|
| LLM 工具循环 | @Tool 注册的工具被 LLM 调用 | `send_emoji` 工具 |
| 用户命令 | @Command 注册的命令被用户触发 | `/weather` 命令 |
| 生命周期 | @HookHandler 在启动/停止时被调用 | `on_load`/`on_unload` |
| 事件总线 | @EventHandler 在事件发生时被调用 | `ON_MESSAGE` 事件 |

---

## 三、三角色与现有机制的关系

### 3.1 Port/Protocol（服务声明）

- `src/core/protocols.py` 定义所有 Protocol 接口
- Protocol 是 `typing.Protocol`（鸭子类型，不强制继承）
- 核心模块只依赖 Protocol，不依赖适配器具体类

### 3.2 适配器层（服务实现）

- `src/core/adapters/` 是唯一允许导入组件具体类的目录
- 适配器在 `main.py` 启动时通过 `set_*()` 注入到 `*_registry`
- 消费方通过 `get_*_port()` 从 registry 获取（运行时多态）

### 3.3 scope（权限控制，ZG16-5）

- scope 是三角色的**权限维度**——声明（manifest scopes）→ 校验（发布端 validate_manifest_scopes）→ 审计（运行时 scope_audit）
- 插件声明 scopes → servicer 握手时校验 → tool_router 执行时审计 Tier 1

### 3.4 depends_on（依赖拓扑，ZG16-3）

- depends_on 是三角色的**依赖维度**——声明（manifest dependencies）→ 解析（拓扑排序）→ 加载（按序启动）

---

## 四、反模式（禁止）

| 反模式 | 正确做法 |
|--------|---------|
| Consumer 直接导入适配器具体类 | Consumer 导入 Protocol，通过 `get_*_port()` 获取 |
| 核心模块导入 `chat_manager` 具体类 | 核心通过 `ChatManagerAdapter` Protocol 交互 |
| 插件直接导入 `global_config` | 插件通过 `ctx.config` 获取配置 |
| 新模块只有定义没有调用点 | 必须接线（@startup_item 或 main.py 显式 init） |
| 绕过 Port 直接调用 send_service | 通过 MessagePort 发送消息 |

---

## 五、测试中的三角色应用

测试时利用三角色切分快速替换 Provider：

```python
# 测试中替换 AppConfigPort 为 Mock
from unittest.mock import patch

def test_with_mock_config():
    with patch("src.core.app_config_port_registry.get_app_config_port",
               return_value=MockAppConfigPort()):
        # Consumer 代码不变，但读取的是 Mock 配置
        ...
```

- Service Definition（Protocol）不变
- Provider 换成 Mock
- Consumer 代码不变——三角色切分的测试优势