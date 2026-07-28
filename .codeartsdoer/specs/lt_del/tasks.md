# LT-DEL: 灵台代码清算 — 任务清单

## DEL-1: 删除模糊修改系统

- [ ] T1.1: 删除 `fuzzy;_modify.py` 和 `feedback_correction.py` 文件
- [ ] T1.2: 清理 `host_service.py` 中 fuzzy_modify/feedback 路由分支和导入
- [ ] T1.3: 清理 `sdk_memory_kernel.py` 中 FeedbackCorrectionService 初始化和调用
- [ ] T1.4: 清理 `metadata_store.py` 中 feedback schema 和 CRUD 方法
- [ ] T1.5: 清理 config 中 feedback/fuzzy_modify 配置项
- [ ] T1.6: 全局搜索残留引用，确保无 dangling import
- [ ] T1.7: ruff 检查通过，提交

## DEL-2: 删除老分类学架构

- [ ] T2.1: 删除 `knowledge_types.py` 和 `type_detection.py` 文件
- [ ] T2.2: 清理 `web_import_manager.py` 中 KnowledgeType/ImportStrategy 引用和分类逻辑
- [ ] T2.3: 清理 `metadata_store.py` 中 knowledge_type 相关方法
- [ ] T2.4: 清理 `sdk_memory_kernel.py` 中 knowledge_type 参数传递
- [ ] T2.5: 清理 `scripts/` 中 knowledge_type 校验逻辑
- [ ] T2.6: 清理其他文件残留引用
- [ ] T2.7: ruff 检查通过，提交

## DEL-3: 删除水库采样训练

- [ ]> T3.1: 删除 `vector_store.py` 中水库采样相关代码
- [ ] T3.2: 验证 VectorStore add/search 仍正常
- [ ] T3.3: ruff 检查通过，提交