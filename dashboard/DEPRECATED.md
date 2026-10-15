# DEPRECATED — dashboard 老前端（冻结保留 · 不再删除）

> 状态：📦 **冻结保留**（原"待废弃"——2026-10-15 更新：**不再计划物理删除**，保留作回退选项）
> 更新理由（lmq 2026-10-15）：git 保底（历史可溯）+ "只修不加"纪律已锁（无维护负担）+ 废弃动作的净收益（~45M 源码）低于保留回退的价值 ⇒ **不删**

## 本目录是什么

- **dashboard/** = MaiBot 老前端（React 19.2 / TS ~5.9.3 / Vite 7.2 / ESLint 9.39）
- **当前生产仍挂载其 dist**：docker-compose `MAIBOT_WEBUI_USE_LOCAL_DASHBOARD=1` + `src/webui/app.py:300` 静态路径

## 废弃状态（重要）

- ⚠️ **新功能开发一律禁止进 dashboard**——新功能一律进 `mingtang/`（新前端，主战场）
- 🔧 dashboard **只做修复不做新功能**（生产还在用，bug 要修）
- 🗓️ **废弃处置（2026-10-15 更新 → 不删除）**：R4 债 ✅ / 三绿 ✅ / 后端挂载 ✅ 均已达成；**本目录不再计划物理删除**——保留作回退（compose 回退旧前端时仍可用）。「功能对照验收」降级为可选质量检查。

## 替代者

- **mingtang/** = 新前端（主战场）——React 19.2 + TS 双轨 / Vite 8.2 / ESLint 10
- 蓝图：`.shared/decisions/WebUI_Plan/mingtang_architecture_blueprint_0808.md`
- 状态说明见项目根 `AGENTS.md`（WebUI 前端状态节）

## 技术差异速查（为什么不能混写）

| 项 | dashboard（老） | mingtang（新） |
|----|----------------|----------------|
| React | 19.2 | 19.2 |
| TypeScript | ~5.9.3 | TS 6.0.2（typescript6 包）+ 7.0.2（native）双轨 |
| Vite | 7.2 | 8.2 |
| ESLint | 9.39 | 10 |
| 验收 | 见其自身 README | `npm run lint && npm run test && npm run build` 三绿 |

**写前端代码前必看**：`AGENTS.md` WebUI 前端状态节 + `.shared/decisions/typescript_new_code_cheatsheet.md`（版本基线警告）。