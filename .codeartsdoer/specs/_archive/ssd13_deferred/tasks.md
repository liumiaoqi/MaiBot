# SSD-13 编码任务：延迟项与架构债务收尾

> 目标：修复 SSD-12 延迟项 G1/G2、send_service.py 已有缺陷 F401/F821、产出整体对象评估报告、更新 AGENTS.md
>
> Codex 典型错误模式提醒（每个批次执行前必读）：
> 1. 替换调用但忘了添加新 import（F821）
> 2. 替换调用但忘了删除旧 import（F401）
> 3. noqa 注释被当成 import 路径的一部分
> 4. 变量替换后后续引用未同步更新
> 5. Windows 环境：PowerShell 不支持 `&&`，用 `;` 或分步执行

## 批次 1：G1 — heuristic_injector.py get_person_id 迁移

> 依赖：无（PersonInfoPort + person_info_port_registry 已由 SSD-12 建立）

- [ ] **T1.1** 迁移 `src/maisaka/memory/heuristic_injector.py` 的 `get_person_id` 直接导入
  - 删除 L17: `from src.person_info.person_info import get_person_id`
  - 新增: `from src.core.person_info_port_registry import get_person_info_port`
  - 修改 `_collect_active_person_ids` 静态方法（3 处调用）：
    - L411: `person_ids.add(get_person_id(platform, user_id))` → `port = get_person_info_port()` + `if port:` 守卫 + `person_ids.add(port.get_person_id(platform, user_id))`
    - L418: `person_ids.add(get_person_id(platform, target_user_id))` → `person_ids.add(port.get_person_id(platform, target_user_id))`
    - L422: `person_ids.add(get_person_id(platform, target_user_id))` → `person_ids.add(port.get_person_id(platform, target_user_id))`
  - 注意：`get_person_info_port()` 返回 `Optional[PersonInfoPort]`，需在方法开头获取一次并守卫 None
  - 验证：`ruff check src/maisaka/memory/heuristic_injector.py` 通过
  - CC/Codex 建议：Codex（1 文件 3 处替换 + 1 处 import 变更，模式明确）

- [ ] **T1.2** 提交批次 1
  - commit message: `refactor: SSD-13 批次1 — heuristic_injector.py get_person_id迁移到PersonInfoPort [CX]`
  - 验证：`ruff check src/maisaka/memory/heuristic_injector.py` 通过

## 批次 2：G2 — test_memory_flow_service.py mock 路径更新

> 依赖：批次 1（G1 完成确认 heuristic_injector 迁移模式正确）
>
> 背景：SSD-12 已将 `memory_flow_service.py` 迁移到 Port（`get_person_info_port()`/`get_app_config_port()`），
> 但测试文件仍 monkeypatch 已不存在的模块级属性，导致测试会失败。

- [ ] **T2.1** 更新 `pytests/A_memorix_test/test_memory_flow_service.py` 的 monkeypatch 目标
  - **get_person_id mock（5 处：L39/L75/L120/L187/L290）**：
    - 删除 `monkeypatch.setattr(memory_flow_module, "get_person_id", ...)` 
    - 改为 `monkeypatch.setattr(memory_flow_module, "get_person_info_port", lambda: FakePersonInfoPort())`
    - `FakePersonInfoPort` 需包含 `get_person_id(platform, user_id)` 方法
  - **Person 类 mock（2 处：L40/L76）**：
    - 删除 `monkeypatch.setattr(memory_flow_module, "Person", FakePerson)`
    - 改为在 `FakePersonInfoPort` 中增加 `get_person_detail(person_id)` 方法，返回 `PersonDetailSnapshot`
    - 测试中访问 `person.person_id` 等属性改为访问 `PersonDetailSnapshot` 的对应字段
  - **store_person_memory_from_answer mock（2 处：L230/L283）**：
    - 删除 `monkeypatch.setattr(memory_flow_module, "store_person_memory_from_answer", ...)`
    - 改为在 `FakePersonInfoPort` 中增加 `async def store_person_memory(...)` 方法
    - 注意：`store_person_memory` 是异步方法，mock 需使用 `async def`
  - **global_config mock（4 处：L313/L363/L402/L513）**：
    - 删除 `monkeypatch.setattr(memory_flow_module, "global_config", _fake_global_config(...))`
    - 改为 `monkeypatch.setattr(memory_flow_module, "get_app_config_port", lambda: FakeAppConfigPort())`
    - `FakeAppConfigPort` 需包含 `get_a_memorix_integration_config()` 方法，返回 `AMemorixIntegrationSnapshot`
  - 注意：部分测试用例（如 L91-131 `test_person_fact_collect_user_evidence_keeps_latest_target_messages_without_reply`）中 `FakePerson()` 仅作为参数传入 `_collect_user_evidence(message, FakePerson())`，需改为构造 `PersonDetailSnapshot(is_known=True, person_id="qq:user-1")` 实例
  - 注意：`_resolve_target_person` 返回值已从 `Optional[Person]` 改为 `Optional[PersonDetailSnapshot]`，测试断言中 `person.person_id` 等属性访问方式不变（`PersonDetailSnapshot` 有同名字段）
  - 验证：`ruff check pytests/A_memorix_test/test_memory_flow_service.py` 通过
  - CC/Codex 建议：CC（7 处 monkeypatch 涉及 4 种 mock 模式，需理解 `PersonDetailSnapshot`/`AMemorixIntegrationSnapshot` 快照结构，且测试断言需同步适配）

- [ ] **T2.2** 运行测试验证
  - `pytest pytests/A_memorix_test/test_memory_flow_service.py -v`
  - 所有测试通过，无 `AttributeError`/`TypeError`
  - CC/Codex 建议：CC

- [ ] **T2.3** 提交批次 2
  - commit message: `test: SSD-13 批次2 — test_memory_flow_service.py mock路径更新到Port [CC]`

## 批次 3：send_service.py F401/F821 缺陷修复

> 依赖：无（独立修改）

- [ ] **T3.1** 修复 `src/services/send_service.py` 的 F401 未使用导入（3 处）
  - 删除 L15: `import base64`
  - 删除 L16: `import hashlib`
  - 从 L41 导入列表删除 `StandardMessageComponents`（保留同行的其他导入）
  - 验证：`ruff check src/services/send_service.py --select F401` 通过

- [ ] **T3.2** 修复 `src/services/send_service.py` 的 F821 未定义名称引用（2 处）
  - L1136: `text_to_stream_with_message` → `_text_to_stream_with_message`
  - L1199: `emoji_to_stream_with_message` → `_emoji_to_stream_with_message`
  - 注意：仅添加下划线前缀，与 L1081/L1151 定义的函数名一致
  - 验证：`ruff check src/services/send_service.py --select F821` 通过

- [ ] **T3.3** 提交批次 3
  - commit message: `fix: SSD-13 批次3 — send_service.py F401/F821缺陷修复 [CX]`
  - 验证：`ruff check src/services/send_service.py` 通过

## 批次 4：收尾（整体对象评估报告 + AGENTS.md 更新）

> 依赖：批次 1-3（所有代码修复完成后）

- [ ] **T4.1** 产出 noqa TID251 整体对象遗留分类报告
  - 写入 `.codeartsdoer/specs/ssd13_deferred/noqa_tid251_evaluation.md`
  - 按 design.md 2.1.3 节分类结果整理 18 处遗留：
    - **可立即拆解（5 处）**：#1 emoji_manager.py / #3 expression_selector.py / #5 reply.py / #14 remote.py / #18 service_task_resolver.py
    - **需新增 Port 方法（7 处）**：#2 mode_utils.py / #4 send_emoji.py / #9 supervisor.py / #10 api.py / #12 emoji_cache_cleanup.py / #13 image_cache_cleanup.py / #15+17 runtime.py+utils_config.py（关联项）
    - **暂不可拆解（6 处）**：#6 routes.py(heartflow_manager) / #7 routes.py(global_config) / #8 config.py / #11 core.py / #16 runtime.py(MCPConfig)
  - 每处包含：文件路径、行号、导入目标、访问属性、分类、理由
  - 验证：报告覆盖全部 18 处，分类完整
  - CC/Codex 建议：CC（需理解各文件的实际属性访问模式，分类判定需准确）

- [ ] **T4.2** 更新 `AGENTS.md`
  - 在"已完成 SSD 摘要"表格添加 SSD-13 行：主题="延迟项与架构债务收尾"，关键成果="G1 heuristic_injector get_person_id迁移到PersonInfoPort + G2 test_memory_flow_service mock路径更新 + send_service.py F401/F821修复 + 整体对象评估报告(5可拆/7需Port/6暂不可拆)"
  - 更新"待后续"清单：
    - 移除 G1/G2（已完成）
    - 新增"noqa TID251 整体对象遗留 18 处（详见 ssd13_deferred/noqa_tid251_evaluation.md）"
    - 保留 A_memorix bare except 309 处
  - CC/Codex 建议：CC

- [ ] **T4.3** 最终验证
  - `ruff check src/` 通过（G1 迁移后无新增 TID251 违规）
  - `ruff check src/services/send_service.py --select F401,F821` 通过（5 处缺陷清零）
  - `pytest pytests/A_memorix_test/test_memory_flow_service.py -v` 通过
  - CC/Codex 建议：CC

- [ ] **T4.4** 提交收尾
  - commit message: `chore: SSD-13 收尾 — 整体对象评估报告+AGENTS.md更新 [CC]`