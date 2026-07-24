"""MaiBot 插件系统 v2 — Phoenix 架构。

与 v1（src/plugin_runtime/）完全隔离，零交叉引用。
三大支柱：MCP Tool/Event 统一组件模型 + OAuth Scope 细粒度授权 + gRPC 标准化传输。
"""