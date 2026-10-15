# AGENTS.md（src/core/）

> 本目录的规矩。核心架构契约（微内核 + 禁止项 14 条）见根 `../AGENTS.md` §一——不在此重复。

## 结构导航

- `protocols.py` — 全部 Protocol 接口定义（找接口先这里）
- `adapters/` — **唯一允许导入组件具体实现**的地方（其他目录只准依赖 Protocol）
- `*_port_registry.py` — 各 Port 的注册点（`set_*()` 由 main.py 启动时注入）
- 子系统目录（control_message / error_escalation / …）— 各自机制

## 改 core 的专属铁律

1. **加 Port 三件套**：Protocol（protocols.py）→ 注册点（`set_*()`）→ **main.py 启动接线**——缺一即静默失效（四连问判据见根 §七）
2. **port_registry 只依赖 Protocol 做类型标注**，不导入适配器具体类（根 §一 第 13 条）
3. **改 Protocol 前先 grep 全部实现与调用方**——核心契约一动，适配器全要跟
4. **新增单例必须补"生产路径初始化"测试**（先例：`tests/unit/core/token_meter/test_wiring.py`）

## 已知坑（完整版见 `docs/pitfalls.md`）

- `TokenMeter 未接线` 类错误 = 单例没被 `@startup_item` 初始化——**不是 bug，是接线缺失**
- `str(Enum)` 比较失效（Python 3.11+）：用枚举成员或 `.value`，禁 `str(enum).lower()`
