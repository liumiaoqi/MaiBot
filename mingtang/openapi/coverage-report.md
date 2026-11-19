# WebUI 契约层报告（v1）

> 本文件由 `contract:report` 自动生成，请勿手改。

## 契约来源与规模

- 来源：`snapshot:openapi/openapi.json`
- 快照取得时间：2026-11-19T08:40:58.121Z
- OpenAPI 版本：3.1.0
- paths：405
- operations：448
- schemas：339
- normalized-sha256：`08e84918f5d6ea579fd615a1cd21cd1387566a28a8bd1e06bf7cb7faffa0b077`
- 口径规则：见下方「统计规则」，共 8 条

## 统计规则

- R1 范围：src/lib/**/*.{ts,tsx}（递归，排除任意 __tests__ 目录与 *.d.ts 声明/生成文件）
- R2 单元 1：单/双引号字符串字面量且值以 /api/ 起始
- R3 单元 2：模板字面量首段为 ${CONST}，CONST 匹配 ^[A-Z][A-Z0-9_]*(BASE|PREFIX|ROOT|URL)$，且同文件存在 const 定义 → 用展开值判定
- R4 单元 3：模板字面量整体文本以 /api/ 起始
- R5 计数：按出现次数计；unique 在全范围合并后去重
- R6 去重键：展开常量后，${...} → {param}，去掉 ? 后的查询串
- R7 不统计：非 /api/ 起始的外部地址、注释文本、测试文件
- R8 规则变更须升 measureVersion，报告双列新旧口径

## CI 与后端漂移的分工

CI 只能守「快照 vs 产物一致」——防的是「改了快照没重生成产物」；「后端真的变了」只在本地后端运行时可见。

**「CI 绿 = 后端没漂移」是误读。**

## 覆盖度四元组

| 指标 | 数值 |
|---|---|
| 操作总数 | 448 |
| 有响应模型 | 214 |
| 无响应模型 | 234 |
| 有请求体模型 | 147 |

恒等式校验：total = withResponseSchema + withoutResponseSchema → 214 + 234 = 448

## 前缀分组

| 分组 | 操作数 | 有响应模型 | 无响应模型 |
|---|---|---|---|
| /api/chat | 15 | 15 | 0 |
| /api/config | 5 | 0 | 5 |
| /api/edge | 3 | 0 | 3 |
| /api/episodes | 5 | 0 | 5 |
| /api/graph | 1 | 0 | 1 |
| /api/import | 25 | 0 | 25 |
| /api/memory | 5 | 0 | 5 |
| /api/node | 3 | 0 | 3 |
| /api/person_profile | 5 | 0 | 5 |
| /api/query | 1 | 0 | 1 |
| /api/retrieval_tuning | 14 | 0 | 14 |
| /api/runtime | 3 | 0 | 3 |
| /api/save | 1 | 0 | 1 |
| /api/source | 3 | 0 | 3 |
| /api/timeline | 1 | 1 | 0 |
| /api/webui | 358 | 198 | 160 |

## 响应模型缺口

缺口条目数：234（仅统计缺响应模型的操作；missing=both 表示同时缺请求体模型）

- `GET /api/config`（/api/config，missing=both）
- `GET /api/config/auto_save`（/api/config，missing=both）
- `POST /api/config/auto_save`（/api/config，missing=response）
- `GET /api/config/schema`（/api/config，missing=both）
- `GET /api/config/schema/bot`（/api/config，missing=both）
- `DELETE /api/edge`（/api/edge，missing=response）
- `POST /api/edge`（/api/edge，missing=response）
- `POST /api/edge/weight`（/api/edge，missing=response）
- `GET /api/episodes`（/api/episodes，missing=both）
- `POST /api/episodes/process_pending`（/api/episodes，missing=response）
- `POST /api/episodes/rebuild`（/api/episodes，missing=response）
- `GET /api/episodes/status`（/api/episodes，missing=both）
- `GET /api/episodes/{episode_id}`（/api/episodes，missing=both）
- `GET /api/graph`（/api/graph，missing=both）
- `GET /api/import/guide`（/api/import，missing=both）
- `POST /api/import/lpmm_convert`（/api/import，missing=response）
- `POST /api/import/lpmm_openie`（/api/import，missing=response）
- `POST /api/import/maibot_migration`（/api/import，missing=response）
- `POST /api/import/paste`（/api/import，missing=response）
- `GET /api/import/path_aliases`（/api/import，missing=both）
- `POST /api/import/raw_scan`（/api/import，missing=response）
- `POST /api/import/resolve_path`（/api/import，missing=response）
- `GET /api/import/settings`（/api/import，missing=both）
- `GET /api/import/tasks`（/api/import，missing=both）
- `POST /api/import/tasks/lpmm_convert`（/api/import，missing=response）
- `POST /api/import/tasks/lpmm_openie`（/api/import，missing=response）
- `POST /api/import/tasks/maibot_migration`（/api/import，missing=response）
- `POST /api/import/tasks/paste`（/api/import，missing=response）
- `POST /api/import/tasks/raw_scan`（/api/import，missing=response）
- `POST /api/import/tasks/temporal_backfill`（/api/import，missing=response）
- `POST /api/import/tasks/upload`（/api/import，missing=both）
- `GET /api/import/tasks/{task_id}`（/api/import，missing=both）
- `POST /api/import/tasks/{task_id}/cancel`（/api/import，missing=both）
- `GET /api/import/tasks/{task_id}/chunks/{file_id}`（/api/import，missing=both）
- `GET /api/import/tasks/{task_id}/files/{file_id}/chunks`（/api/import，missing=both）
- `POST /api/import/tasks/{task_id}/retry`（/api/import，missing=response）
- `POST /api/import/tasks/{task_id}/retry_failed`（/api/import，missing=response）
- `POST /api/import/temporal_backfill`（/api/import，missing=response）
- `POST /api/import/upload`（/api/import，missing=both）
- `POST /api/memory/freeze`（/api/memory，missing=response）
- `POST /api/memory/protect`（/api/memory，missing=response）
- `GET /api/memory/recycle_bin`（/api/memory，missing=both）
- `POST /api/memory/reinforce`（/api/memory，missing=response）
- `POST /api/memory/restore`（/api/memory，missing=response）
- `DELETE /api/node`（/api/node，missing=response）
- `POST /api/node`（/api/node，missing=response）
- `POST /api/node/rename`（/api/node，missing=response）
- `GET /api/person_profile/list`（/api/person_profile，missing=both）
- `POST /api/person_profile/override`（/api/person_profile，missing=response）
- `DELETE /api/person_profile/override/{person_id}`（/api/person_profile，missing=both）

… 其余 184 条见 gaps.json

## 无形状端点

有 2xx 响应但 application/json schema 为空或缺失的端点（生成器无法据此产出类型）。

- `GET /api/config`
- `GET /api/config/auto_save`
- `POST /api/config/auto_save`
- `GET /api/config/schema`
- `GET /api/config/schema/bot`
- `DELETE /api/edge`
- `POST /api/edge`
- `POST /api/edge/weight`
- `GET /api/episodes`
- `POST /api/episodes/process_pending`
- `POST /api/episodes/rebuild`
- `GET /api/episodes/status`
- `GET /api/episodes/{episode_id}`
- `GET /api/graph`
- `GET /api/import/guide`
- `POST /api/import/lpmm_convert`
- `POST /api/import/lpmm_openie`
- `POST /api/import/maibot_migration`
- `POST /api/import/paste`
- `GET /api/import/path_aliases`
- `POST /api/import/raw_scan`
- `POST /api/import/resolve_path`
- `GET /api/import/settings`
- `GET /api/import/tasks`
- `POST /api/import/tasks/lpmm_convert`
- `POST /api/import/tasks/lpmm_openie`
- `POST /api/import/tasks/maibot_migration`
- `POST /api/import/tasks/paste`
- `POST /api/import/tasks/raw_scan`
- `POST /api/import/tasks/temporal_backfill`
- `POST /api/import/tasks/upload`
- `GET /api/import/tasks/{task_id}`
- `POST /api/import/tasks/{task_id}/cancel`
- `GET /api/import/tasks/{task_id}/chunks/{file_id}`
- `GET /api/import/tasks/{task_id}/files/{file_id}/chunks`
- `POST /api/import/tasks/{task_id}/retry`
- `POST /api/import/tasks/{task_id}/retry_failed`
- `POST /api/import/temporal_backfill`
- `POST /api/import/upload`
- `POST /api/memory/freeze`
- `POST /api/memory/protect`
- `GET /api/memory/recycle_bin`
- `POST /api/memory/reinforce`
- `POST /api/memory/restore`
- `DELETE /api/node`
- `POST /api/node`
- `POST /api/node/rename`
- `GET /api/person_profile/list`
- `POST /api/person_profile/override`
- `DELETE /api/person_profile/override/{person_id}`

## 宽对象端点

响应 schema 为 object 且没有 properties 的端点（类型只能退化为 Record<string, unknown>）。

- `DELETE /api/chat/history`
- `GET /api/chat/history`
- `GET /api/chat/info`
- `GET /api/chat/persons`
- `GET /api/chat/platforms`
- `GET /api/chat/resolve-target`
- `POST /api/chat/resolve-targets`
- `GET /api/chat/sessions`
- `DELETE /api/chat/sessions/{session_id}`
- `GET /api/chat/sessions/{session_id}`
- `PUT /api/chat/sessions/{session_id}/learning/{kind}`
- `PUT /api/chat/sessions/{session_id}/prompts`
- `DELETE /api/chat/sessions/{session_id}/prompts/{index}`
- `DELETE /api/chat/sessions/{session_id}/talk-frequency`
- `PUT /api/chat/sessions/{session_id}/talk-frequency`
- `DELETE /api/webui/chat/history`
- `GET /api/webui/chat/history`
- `GET /api/webui/chat/info`
- `GET /api/webui/chat/persons`
- `GET /api/webui/chat/platforms`
- `GET /api/webui/chat/resolve-target`
- `POST /api/webui/chat/resolve-targets`
- `GET /api/webui/chat/sessions`
- `DELETE /api/webui/chat/sessions/{session_id}`
- `GET /api/webui/chat/sessions/{session_id}`
- `PUT /api/webui/chat/sessions/{session_id}/learning/{kind}`
- `PUT /api/webui/chat/sessions/{session_id}/prompts`
- `DELETE /api/webui/chat/sessions/{session_id}/prompts/{index}`
- `DELETE /api/webui/chat/sessions/{session_id}/talk-frequency`
- `PUT /api/webui/chat/sessions/{session_id}/talk-frequency`
- `POST /api/webui/emoji/batch/upload`
- `GET /api/webui/emoji/stats/summary`
- `GET /api/webui/expression/stats/summary`
- `PATCH /api/webui/log/levels`
- `GET /api/webui/log/search`
- `GET /api/webui/log/status`
- `GET /api/webui/log/think-cycles`
- `GET /api/webui/person/stats/summary`
- `GET /api/webui/plugins/config/{plugin_id}`
- `PUT /api/webui/plugins/config/{plugin_id}`
- `GET /api/webui/plugins/config/{plugin_id}/bundle`
- `GET /api/webui/plugins/config/{plugin_id}/raw`
- `PUT /api/webui/plugins/config/{plugin_id}/raw`
- `POST /api/webui/plugins/config/{plugin_id}/reset`
- `GET /api/webui/plugins/config/{plugin_id}/schema`
- `POST /api/webui/plugins/config/{plugin_id}/toggle`
- `POST /api/webui/plugins/install`
- `GET /api/webui/plugins/installed`
- `GET /api/webui/plugins/local-changelog/{plugin_id}`
- `GET /api/webui/plugins/local-readme/{plugin_id}`

## 手写路径基线（口径 v1，本期只记录基线）

- 口径版本：`v1`
- 覆盖范围：src/lib/**（排除 __tests__）
- 出现次数：**211**
- unique 数：**179**
- 复算命令：`NODE_OPTIONS= pnpm run contract:report`

> 历史记录 107 / 93 为口径未固化时期的数字，**不可复算、不可与新值直接比较**，仅作留档。
> 本期验收只要求基线记录完整（spec §9 第 5 条）；「路径字面量减少」不在本期验收范围。

### 分文件出现次数

| 文件 | 次数 |
|---|---|
| agent-api.ts | 40 |
| auth.ts | 2 |
| avatar-url.ts | 1 |
| chat-management-api.ts | 10 |
| config-api.ts | 18 |
| deepseek-api.ts | 7 |
| emoji-api.ts | 18 |
| expression-api.ts | 25 |
| jargon-api.ts | 10 |
| memory-api.ts | 2 |
| migration-api.ts | 1 |
| pack-api.ts | 4 |
| person-api.ts | 7 |
| plugin-api/config.ts | 11 |
| plugin-api/home-cards.ts | 1 |
| plugin-api/install-flow.ts | 3 |
| plugin-api/installed.ts | 3 |
| plugin-api/marketplace.ts | 3 |
| plugin-stats.ts | 8 |
| prompt-api.ts | 7 |
| prompt-generator-api.ts | 2 |
| reasoning-process-api.ts | 7 |
| restart-context.tsx | 1 |
| statistics-api.ts | 3 |
| system-api.ts | 16 |
| unified-ws.ts | 1 |

## 历史数字纠偏

- 决策文档 `webui_contract_codegen_1019.md` 的「315 个端点」已失效：当前实测为 405 paths / 448 operations / 339 schemas。
- 决策文档的「9 个域手抄 fetch」不成立：裸 fetch 仅 5 处 / 4 文件；真实痛点是路径字面量与手写类型规模。
- 旧路径基线 107 / 93 因口径未固化不可复算，已由口径 v1 取代。
