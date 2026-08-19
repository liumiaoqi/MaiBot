## Engineering Context

```json
{
  "Language Context": [
    "Python"
  ]
}
```

## Skill 库使用引导（2026-08-19 更新——克隆池 5 库盘点 + dsh 团队 11）

> 完整版：`.shared/decisions/clone_skill_library_guide_0819.md`（含逐库精华映射 + 落地三步 + 诚实清单）
> 原则：**skill 是方法不是圣经**——引入前问"它解决我们哪个具体痛点"，不为了用而用。

### 一、你写 SSD/调研/审查时优先参考的 skill

| 场景 | 参考 skill | 位置 |
|------|-----------|------|
| SSD spec 编写 | spec-driven-development / to-spec | agent-skills/、skills/ |
| 双轴审核（Standards+Spec） | code-review | skills/ |
| 关键决策对抗审查 | **doubt-driven-development**（biased to disprove） | agent-skills/ |
| 安全相关代码/配置 | security-and-hardening | agent-skills/ |
| 废弃/迁移流程 | deprecation-and-migration | agent-skills/ |
| 交接文档 | handoff（带 suggested-skills 节） | skills/ |
| 排障 | diagnosing-bugs | skills/ |
| 科学实验/统计 | experimental-design / statistical-analysis | scientific-agent-skills/ |
| 文献综述/调研 | literature-review / research-lookup | scientific-agent-skills/ |
| 代码审计/安全逆向 | code-audit / llm-security | reverse-skill/ |

### 二、dsh 团队 11 个内置 skill（工作流即插件——harness 作者日常用）

- 工程纪律：code-review / pre-push-checks（**只跑覆盖本次 diff 的最小测试**，验收才全量）/ find-simplifications / archive-agent-notes
- 文档体系：doc-standards / prose-standard（**先写保留契约，再删推理转述**）/ translate-docs / doc-site-sync
- 质量专项：**trim-cot-leakage**（防注释/文档残留会话视角——审文档时查 "(decision N)"/"后来 PR 里" 这类）
- 流程工具：merging-stacked-prs / record-browser-gif

### 三、协作规则速查（CA 视角）

- **handoff 交接**：写"建议先读"（已有）**+"建议 skill"**（新增——引导下一个 agent 用什么工作流）
- **SSD 三件套**：spec（需求+DFX+验收）→ design（决策+改动点+测试接缝）→ tasks（可执行+验证命令）
- **审核视角**：非平凡决策（跨模块/不可逆/安全敏感）先质疑再定稿——"这个决策的哪个假设最可疑？"
- **代码事实优先**：文档里出现的 SQL/字段名/行号必须对代码核实（ZG-29 审核教训：src_id→source_node_id）
- **git 纪律**：及时提交；commit message 末尾加 [CA]；喜欢 git log --graph
- **不在 main 干活**：worktree 隔离，合并前确认
- **不评估工时**（用户不喜欢报工期）
