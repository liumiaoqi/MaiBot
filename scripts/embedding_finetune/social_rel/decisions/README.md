# social_rel 决策索引（2026-09-27）

> ⚠️ **这是领域内的索引，不是中央表**（`hub CONVENTIONS.md §9.3`「索引进中枢 / 正文留领域」的**例外**：
> 本索引只服务 `social_rel` 这一条线，方便"寒假重启"时**一页看懂定过什么**）✓
> 现场全记录（含每条结论的命令与原始输出）：`../NOTES.md`（2236 行）· 要你拍的点：`../DECISIONS-WANTED.md`

| 文档 | 一句话 | 状态 |
|---|---|---|
| `2026-09-27-relation-strength-truth-loop.md` | **关系强度没有真值，唯一通路是显式反馈回路**（S1 保留 / S2 回滚 / 0004 已落地机制）| `accepted` · 机制 `implemented` |
| `2026-09-27-memory-wiring-defects.md` | **四处接线缺陷**及处置（552 屏蔽 · `running` 死状态 · 端点补建 · 人–人缺路径）| `implemented` |
| `2026-09-27-field-and-delivery-closures.md` | **场方向到此为止**（控制度后归零）＋ 使命两半都缺料 ＋ B 线收口 ＋ 交付三件 | `accepted` |
| `2026-09-27-shared-submodule-question.md` | `.shared` **能不能转标准子模块**（回答 lmq 两问；建议留到寒假重启那轮一起拍）| `proposed` |

## 与别处记录的关系（别重复读）

| 想了解 | 去哪 |
|---|---|
| 每条结论的**原始输出与命令** | `../NOTES.md`（§0–§1.46）|
| **要 lmq 拍的点**（当前只剩 0004 的用户入口）| `../DECISIONS-WANTED.md` |
| 四份**申请**（0001–0004，含判据/回滚）| `../proposals/` |
| B 线（按论文组织）的预登记与结论 | `../sat/PILOT.md` §十二 |
| 接线审计工具（含正/负对照，可一键复跑）| `../tools/audit_wiring.py` |
| `.shared` 的形态决策（WB 原决策）| `.shared/decisions/2026-09-24-shared-gitlink-decision.md` |

## 重启时的**最短路径**（3 步）

1. 读本页 → 知道定过什么 ✓
2. 读 `../DECISIONS-WANTED.md` 的「已执行」块 → 知道**已经落地了什么**（8 项，各带一条证据 ✓）
3. 要动核心前先读 `../proposals/0004-*.md`（唯一未接线的那件：**用户入口**）✓
