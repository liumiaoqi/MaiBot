# graph_ops — 已废弃

**状态：DEPRECATED（NEW_INDEPENDENT 阶段）**

此目录包含分类学记忆系统的代码（Paragraph/Entity/Relation/Episode/Profile）。

记忆系统范式迁移已完成至 NEW_INDEPENDENT 阶段：
- 分类学代码保留但不再调用
- 所有请求走连接主义系统（`src/A_memorix/core/connectionist/`）
- 核心模块零导入此目录（ruff TID251 守卫）

此目录将在 6 个月后删除。请勿新增对此目录的导入。
