# AGENTS.md（src/A_memorix/）

> 记忆子系统。**核心隔离与接口契约的完整约束在 `MODIFICATION_POLICY.md`（必读）**——不在此重复。

- 可自由修改；约束仅来自：**核心隔离**（不依赖 core 内部）+ **Protocol 接口契约**
- 配置参考：`CONFIG_REFERENCE.md` · 导入指南：`IMPORT_GUIDE.md` · 变更史：`CHANGELOG.md`
- 关联实验线：`scripts/embedding_finetune/social_rel/`（社会关系强度学习）——产物反哺本模块设计
