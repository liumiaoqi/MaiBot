# DEPRECATED — dashboard 老前端（即将废弃）

> 状态：⚠️ 遗留——待 mingtang 验收后废弃（2026-08-21 立）

## 本目录是什么

- **dashboard/** = MaiBot 老前端（React 19.2 / TS ~5.9.3 / Vite 7.2 / ESLint 9.39）
- **当前生产仍挂载其 dist**：docker-compose `MAIBOT_WEBUI_USE_LOCAL_DASHBOARD=1` + `src/webui/app.py:300` 静态路径

## 废弃状态（重要）

- ⚠️ **新功能开发一律禁止进 dashboard**——新功能一律进 `mingtang/`（新前端，主战场）
- 🔧 dashboard **只做修复不做新功能**（生产还在用，bug 要修）
- 🗓️ **废弃时机**：mingtang 完成 R4 债清理 + 三绿验收（lint/test/build）+ 后端挂载切换 + 功能对照验收后，本目录整体删除

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