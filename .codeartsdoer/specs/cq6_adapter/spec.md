# CQ-6: napcat-adapter 插件化迁移 + v2 EventDispatcher 闭环

## 目标

闭环 v2 EventDispatcher，使 napcat-adapter 以 v4 插件形式运行时，QQ 消息能从 WS 入站经 emit_event 路由到 MessageIngestionPort.receive_message()，恢复 MaiBot 收发 QQ 消息的能力。

## 现状分析

### v2 EventDispatcher 缺口

`src/plugin_runtime_v2/mcp/event_dispatcher.py` 的 `dispatch()` 是 Phoenix-2 桩实现，只做日志记录，不路由到任何核心接口。

关键缺陷：
1. `__init__` 接受 `message_port`、`session_repo`、`person_info_port` 参数，但从未使用
2. `bootstrap.py` 创建 EventDispatcher 时未注入任何 Port：`event_dispatcher = EventDispatcher()`
3. 两个 TODO：Phoenix-4 实现 WebUI 转发、ThinkingOrgan.think_proactive() 对接

### napcat-adapter 注册清单

**5 个 @Tool**（出站）：`napcat.send_text`、`send_image`、`send_emoji`、`send_forward`、`send_hybrid`

**0 个 @Event 声明** — 但运行时 emit 了 3 种事件：`napcat.message`、`napcat.group_message`、`napcat.notice`

这是核心缺口：插件 emit 了事件但未用 @Event 装饰器声明，导致 Host 端查不到声明，on_event_received() 直接返回。

### manifest 兼容性

| 维度 | v1 运行时 | v2 运行时 |
|------|----------|----------|
| 文件名 | `_manifest.json` | `manifest.json` |
| manifest_version | 2 | 3 |
| SDK 基类 | v1 本地 SDK | `MaiBotPlugin` (v4) |

napcat-adapter 用 `manifest.json` + v3 + MaiBotPlugin → 仅 v2 运行时可加载，v1 无法识别。

### 消息管道 5 处断点

```
napcat-adapter._handle_message_event()
  → ctx.emit_event("napcat.message", payload)     ✅
    → RunnerEndpoint.emit_event() → gRPC          ✅
      → HostServicer → on_event_received()        ✅
        → MCPHostBridge.on_event_received()       ✅
          → 查 _event_declarations[event_name]     ❌ 断点1: 未声明
          → EventDispatcher.dispatch()             ❌ 断点2: 桩实现
            → MessageIngestionPort.receive_message() ❌ 断点3: 未注入 Port
              → SessionMessage 构造                ❌ 断点4: payload→SessionMessage 转换缺失
                → 核心消息处理管道                 ✅
```

断点5：v2 运行时默认关闭 + Runner 入口不加载插件。

## 需求

### R1: v2 EventDispatcher 闭环
EventDispatcher.dispatch() 对消息类 Event 路由到 MessageIngestionPort.receive_message()。

### R2: napcat-adapter Event 声明补全
为 3 个运行时 emit 事件补上 @Event 装饰器/声明。

### R3: v2 Runner 入口补全插件加载
Runner entrypoint 从 --plugin-dir 发现并加载 MaiBotPlugin 子类。

### R4: v2 运行时默认启用
PluginRuntimeV2Config.enabled 默认值改为 True。

### R5: 消息通路端到端验证
集成测试验证完整链路。

## 验收标准

| 需求 | 验收条件 |
|------|---------|
| R1 | dispatch() 对 napcat.message/napcat.group_message 调用 MessageIngestionPort.receive_message()，SessionMessage 字段正确 |
| R1 | dispatch() 对非消息 Event 保持原有日志行为 |
| R2 | PluginLoader 扫描后收集到@3 个 Event 声明 |
| R2 | MCPHostBridge._event_declarations 包含 napcat.message 等 |
| R3 | Runner entrypoint 从 --plugin-dir 成功加载 MaiBotPlugin |
| R4 | v2 enabled=True 时 napcat-adapter 被加载运行 |
| R5 | 端到端：模拟 OneBot 11 payload → 验证 receive_message() 被调用 |

## 风险

| 风险 | 缓解 |
|------|------|
| event payload → SessionMessage 转换丢字段 | 对照 v1 MessageGateway.build_session_message() 逐一验证 |
| v1/v2 共存消息重复入站 | v1 不加载 napcat-adapter（无 _manifest.json），自然隔离 |
| EventDispatcher 注入 Port 时序 | 延迟注入：持获取函数，dispatch 时解析 |
| napcat-adapter Tool 通路 | 已闭环：gRPC InvokeTool → Runner → plugin.tool → transport.call_action() |

## 实现优先级

1. R2（Event 声明补全）— 最小改动
2. R1（EventDispatcher 闭环）— 核心改动
3. R3（Runner 入口补全）— 使 v2 能加载插件
4. R4（默认启用）— 配置层
5. R5（端到端验证）— 最后