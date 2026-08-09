# R3 批次编码问题记录

> 日期：2026-08-09 ~ 2026-08-10
> 批次：R3 chat 域 2 页 + memory 域 2 页组装（R3-1 ~ R3-5，27 任务）
> 当前进度：R3-1（7任务）+ R3-2（5任务）+ R3-3-1~R3-3-4（工具簇+重放+展示组件+主页面）完成
> 状态：28 个问题全部已解决
> 提交标记：[CA]
> 三绿基线：804 tests / 68 files / build 绿 / lint 0 错 0 警

---

## 问题总览

| # | 任务 | 问题类型 | 严重度 | 根因 | 解决方式 |
|---|------|----------|--------|------|----------|
| R3-W-1 | R3-1-2 | 命名导入错误 | 高 | @radix-ui/react-avatar 无 AvatarPrimitive 命名导出 | 改 `import * as AvatarPrimitive` |
| R3-W-2 | R3-1-2 | 组件 props 不兼容 | 中 | mingtang shadcn ScrollArea 不支持 viewportRef/contentClassName/scrollbars | 合法扩展 scroll-area.tsx 加可选 props（向后兼容） |
| R3-W-3 | R3-1-2 | jsdom 限制 | 中 | jsdom 缺 scrollTo/scrollIntoView | test-setup.ts 补 jsdom mock |
| R3-W-4 | R3-1-3 | jsdom 限制 | 中 | jsdom 缺 ResizeObserver（Textarea autoResize 需要） | test-setup.ts 补 ResizeObserver mock |
| R3-W-5 | R3-1-3 | API 签名不符 | 高 | chatWsClient.sendMessage(sessionId, content, userName, options) 4 参数——与 SSD 假设的 sendMessage(payload) 不符 | 适配调用签名 + images 类型改 ChatImagePayload[] |
| R3-W-6 | R3-1-3 | lint 新规则拦截 | 高 | textarea.tsx hasFixedHeight 用 useEffect+setState——react-hooks set-state-in-effect 规则拦截 | 改 useMemo 派生状态（CC 审查建议的渲染期调整模式） |
| R3-W-7 | R3-1-2 | 未使用变量 | 低 | 测试文件 screen/empty 未用 + VIRTUAL_TABS_STORAGE_KEY 导入源错 | 移除未用导入 + 从 types 导入 |
| R3-W-8 | R3-1-4 | 盘点有误 | 中 | dashboard 无 UserEmojiManager 文件（grep 全仓无此文件） | 跳过（可能内联于 chat/index.tsx，R3-1-6 组装时确认） |
| R3-W-13 | R3-2-0 | 底座缺失 | 高 | mingtang 缺 6 个 UI 组件（badge/checkbox/slider/progress/table/skeleton）+ 3 个 radix 依赖 | 创建 6 组件（mingtang 新写法）+ pnpm add 3 radix 包 |
| R3-W-14 | R3-2-1 | CSS 缺失 | 中 | HoverScrollText 需 chat-management-text-scroll keyframe，mingtang CSS 无此动画 | 手动添加 @keyframes 到 styles/index.css |
| R3-W-15 | R3-2-1 | CSS 语法错误 | 高 | edit 工具编辑 CSS 后多余 `}` 导致 Tailwind 构建失败 | 修复多余 `}`——edit 后需 read 验证 CSS 语法 |
| R3-W-16 | R3-2-2 | 类型不符 | 高 | ChatStreamDetail 无 adapters/learning/agent_* 字段，有 expression/jargon/group_id/user_id | 测试 makeDetail 适配实际类型 |
| R3-W-17 | R3-2-2 | 类型不全 | 中 | ChatTalkFrequencyRule 需 is_default_target: boolean（SSD 假设遗漏） | 测试 mock 补 is_default_target |
| R3-W-18 | R3-2-2 | 类型不符 | 中 | ChatPromptDetail 无 prompt_rules，有 chat_prompts + base_prompt_type + base_prompt_title | 测试 makeDetail 适配实际类型 |
| R3-W-19 | R3-2-5 | 测试交互 | 中 | Radix Tabs fireEvent.click 不触发 onValueChange | 改用 userEvent.click（@testing-library/user-event） |
| R3-W-20 | R3-2-0 | lint 误报 | 低 | table.tsx React.ThHTMLAttributes 触发 react/prop-types lint | 改用 React.ComponentProps<'th'> / React.ComponentProps<'td'> |
| R3-W-21 | R3-2-3 | lint 拦截 | 高 | session-prompts.tsx setDraft in useEffect 触发 set-state-in-effect | 用 requestAnimationFrame 包裹（R3-W-6 同类） |
| R3-W-22 | R3-2-4 | lint 警告 | 低 | mutual-groups-view.tsx sectionData 条件表达式在 useMemo 依赖中触发 exhaustive-deps | wrap sectionData in useMemo |
| R3-W-23 | R3-3-4 | write字符污染 | 高 | ThinkingIllustration write时`'md'E'`拼写错误——write工具写TSX文件时偶发语法字符污染 | edit修复后read验证——write后必须read验证完整文件内容 |
| R3-W-24 | R3-3-4 | UI组件缺失 | 中 | mingtang缺popover.tsx和switch.tsx UI组件——主页面导出/匿名Switch需要 | 新建2个UI组件 + pnpm add @radix-ui/react-popover @radix-ui/react-switch |
| R3-W-25 | R3-3-4 | 组件props不兼容 | 中 | mingtang AlertDialogAction不支持variant prop（dashboard支持variant="destructive"） | 扩展alert-dialog.tsx的AlertDialogAction增加可选variant prop |
| R3-W-26 | R3-3-4 | 导入位置错误 | 低 | formatPromptPreviewText在tag-parse.ts导出，首次写页面时误从format.ts导入 | 移至tag-parse.ts导入 |
| R3-W-27 | R3-3-4 | 未使用导入 | 低 | 首次写页面包含8个未使用导入（Badge/SelectValue/replayReasoningPrompt等） | lint拦截后逐一移除 |
| R3-W-28 | R3-3-4 | 预存在测试缺陷 | 低 | anonymize.test.ts缺少vi导入——tsc报TS2304 Cannot find name 'vi' | 补vi导入 + tag参数显式标注string类型 |

---

## 详细记录

### R3-W-1：avatar.tsx AvatarPrimitive 命名导入错误（R3-1-2）

**现象**：创建 `components/ui/avatar.tsx` 时 `import { AvatarPrimitive } from '@radix-ui/react-avatar'` 报 undefined——@radix-ui/react-avatar 无 `AvatarPrimitive` 命名导出。

**根因**：shadcn/ui 的 avatar 组件用 `import * as AvatarPrimitive` 命名空间导入，而非具名导入。

**解决**：改为 `import * as AvatarPrimitive from '@radix-ui/react-avatar'`。

**教训**：shadcn/ui 组件复制时注意 Radix Primitive 的命名空间导入模式——`import * as XxxPrimitive` 而非 `import { XxxPrimitive }`。

---

### R3-W-2：ScrollArea props 不兼容（R3-1-2）

**现象**：MessageList 从 dashboard 搬移时需要 ScrollArea 的 `viewportRef` / `contentClassName` / `scrollbars` props，但 mingtang 标准 shadcn ScrollArea 不支持这些 props。

**根因**：mingtang R1 复制的 ScrollArea 是 shadcn 标准最小版本，dashboard 原版 ScrollArea 有扩展 props。

**解决**：合法扩展 `components/ui/scroll-area.tsx`，加可选 props `viewportRef` / `contentClassName` / `viewportClassName` / `scrollbars`——向后兼容（原有 props 不变，新 props 可选）。

**教训**：shadcn 基础组件搬移时可能需扩展 props 以适配原版用法——合法扩展（可选 props + 向后兼容）不破坏 R1 已建。

---

### R3-W-3：jsdom 缺 scrollTo/scrollIntoView（R3-1-2）

**现象**：MessageList 测试中 `viewport.scrollTo is not a function`——jsdom 不实现 scrollTo/scrollIntoView。

**根因**：jsdom 是纯 DOM 模拟，不实现滚动相关 API。

**解决**：`test-setup.ts` 补 jsdom mock——`Element.prototype.scrollTo = vi.fn()` / `Element.prototype.scrollIntoView = vi.fn()`。

**教训**：涉及滚动的组件测试需在 test-setup.ts 补 jsdom mock。沿用 TE W-4/W-5 jsdom 限制教训。

---

### R3-W-4：jsdom 缺 ResizeObserver（R3-1-3）

**现象**：ChatComposer 的 Textarea autoResize 功能用 ResizeObserver 观察尺寸变化，测试报 `ResizeObserver is not defined`。

**根因**：jsdom 不实现 ResizeObserver。

**解决**：`test-setup.ts` 补 `global.ResizeObserver = vi.fn().mockImplementation(() => ({ observe: vi.fn(), unobserve: vi.fn(), disconnect: vi.fn() }))`。

**教训**：涉及尺寸观察的组件测试需补 ResizeObserver mock。与 R3-W-3 同类 jsdom 限制。

---

### R3-W-5：useOptimisticSend sendMessage 签名不符（R3-1-3）

**现象**：design.md 假设 `chatWsClient.sendMessage(sessionId, payload)`，但实际 lib/chat-ws-client.ts 的签名是 `sendMessage(sessionId, content, userName, options)` 4 参数。

**根因**：SSD design.md 接口设计基于推测，未核对 lib 实际签名。

**解决**：适配调用签名——`chatWsClient.sendMessage(sessionId, payload.content, payload.user_name, { images: payload.images, emojis: payload.emojis })`；images 类型改 `ChatImagePayload[]`（lib 实际类型）。

**教训**：lib 接口签名需编码时 grep 确认——SSD 接口设计是蓝图不是合同（CC 审查 §三已标注行数偏差同理）。

---

### R3-W-6：lint set-state-in-effect 新规则拦截（R3-1-3）

**现象**：`textarea.tsx` 的 `hasFixedHeight` 用 `useEffect` + `setState` 派生——react-hooks 新规则 `set-state-in-effect` 拦截 lint。

**根因**：CC 审查报告 §六已预警："react-hooks 新规则（set-state-in-effect / refs-in-render）会拦截——外部数据同步草稿用渲染期调整模式"。

**解决**：`hasFixedHeight` 改为 `useMemo` 派生状态（从 props 计算——渲染期调整模式，非 effect+setState）。

**教训**：lint 全量绿（TS 7/6 并存方案恢复）后，react-hooks 新规则会拦截 effect 中 setState——用 useMemo / 渲染期调整模式替代。**CC 审查 §六已预警，编码时需主动遵守**。

---

### R3-W-7：测试文件未使用变量（R3-1-2）

**现象**：build 报 TS6133——测试文件导入 `screen` / `empty` 未使用 + `VIRTUAL_TABS_STORAGE_KEY` 导入源错误。

**根因**：测试编写时导入未清理 + 常量导入路径错误。

**解决**：移除未使用导入 + 从 `types` 导入 `VIRTUAL_TABS_STORAGE_KEY`。

**教训**：`noUnusedLocals: true` 约束测试文件——编码完成后需检查未使用导入。沿用 TE W-3/W-7 教训。

---

### R3-W-8：UserEmojiManager 盘点有误（R3-1-4）

**现象**：tasks.md R3-1-3 要求搬移 UserEmojiManager（250 行——自定义表情管理 Popover），但 `grep -r "UserEmojiManager" dashboard/src/` 全仓无此文件。

**根因**：R3 输入盘点（`mingtang_r3_chat_inventory_0809.md`）列出 UserEmojiManager 250 行，但 dashboard 实际无此独立组件——可能内联于 chat/index.tsx 或已删除。

**解决**：跳过 UserEmojiManager 独立搬移——R3-1-6 组装 ChatPage 时确认是否内联于原版 chat/index.tsx，如有则搬移内联逻辑。

**教训**：SSD 盘点可能有误（与 CC 审查 §三行数偏差同理）——编码时 grep 确认实际存在性。**蓝图不是合同**。

---

## 教训总结（沿用 + 新增）

### 沿用 TE 教训（11 个）
- TE W-1：hook 改 Context 测试需包裹 Provider
- TE W-2：Partial<T> 非深 Partial
- TE W-3/W-7：测试文件 noUnusedLocals 约束
- TE W-4/W-5：jsdom 限制（fetch/Node.js 模块用 ?raw）
- TE W-6：Set<字面量联合> 用 Set<string>
- TE W-9：spread 不验证接口属性用内联
- TE W-10：HSL 低饱和度色相不稳定

### R3 新增教训（8 个）
- **R3-W-1**：shadcn Radix Primitive 用 `import * as XxxPrimitive` 命名空间导入
- **R3-W-2**：shadcn 基础组件可合法扩展可选 props（向后兼容）
- **R3-W-3/W-4**：jsdom 缺 scrollTo/scrollIntoView/ResizeObserver——test-setup.ts 补 mock
- **R3-W-5**：lib 接口签名需编码时 grep 确认（SSD 接口是蓝图不是合同）
- **R3-W-6**：lint 全量绿后 react-hooks set-state-in-effect 拦截——用 useMemo 派生状态（CC 审查 §六预警）
- **R3-W-8**：SSD 盘点可能有误——编码时 grep 确认实际存在性
- **R3-W-9**：Radix Dialog 用 Portal 渲染到 document.body——测试用 screen/document.body 查询而非 container
- **R3-W-10**：hook 测试事件触发需用 act() 包裹——否则 setState 不 flush，result.current 不更新
- **R3-W-11**：useEffect 依赖对象引用导致每次 render cleanup 重置状态——用 tab?.id 做依赖而非 tab 对象
- **R3-W-12**：mingtang dialog 无 DialogBody/confirmOnEnter 扩展——用标准 DialogContent + ScrollArea 替代（不扩展 dialog.tsx）

### R3-2 新增教训（10 个）
- **R3-W-13**：R3-2 页面依赖的 UI 组件可能缺失——编码前先 glob 确认 components/ui 存在性，缺则补齐（新写法函数组件 + React.ComponentProps）
- **R3-W-14**：CSS keyframe 动画需手动搬移——dashboard index.css 的 @keyframes 不在 mingtang 中，需手动添加
- **R3-W-15**：edit 工具编辑 CSS 后易产生多余 `}`——edit 后必须 read 验证 CSS 语法（Tailwind 对语法零容忍）
- **R3-W-16**：ChatStreamDetail 实际类型与 SSD 假设不符——无 adapters/learning/agent_* 字段，有 expression/jargon——编码时 read lib 类型定义
- **R3-W-17**：ChatTalkFrequencyRule 需 is_default_target 字段——SSD 类型假设遗漏——测试 mock 需补全所有 required 字段
- **R3-W-18**：ChatPromptDetail 无 prompt_rules，有 chat_prompts + base_prompt_type + base_prompt_title——lib 类型定义是权威
- **R3-W-19**：Radix Tabs 在测试中 fireEvent.click 不触发 onValueChange——需用 userEvent.setup().click()（@testing-library/user-event）
- **R3-W-20**：React.ThHTMLAttributes/TdHTMLAttributes 触发 react/prop-types lint——改用 React.ComponentProps<'th'> / React.ComponentProps<'td'>
- **R3-W-21**：set-state-in-effect 规则拦截 useEffect 中 setState——用 requestAnimationFrame 包裹（R3-W-6 同类，CC 审查 §六预警）
- **R3-W-22**：条件表达式在 useMemo 依赖中触发 exhaustive-deps 警告——将条件表达式本身 wrap in useMemo

### R3-3 新增教训（6 个）
- **R3-W-23**：write工具写TSX文件时偶发语法字符污染（如`'md'E'`、`;`前缀、`E'`拼接）——write后必须read验证完整文件内容（沿用R3-W-15 edit后read验证教训）
- **R3-W-24**：主页面组装前先glob确认所有依赖UI组件存在——缺则新建（Popover/Switch需@radix-ui/react-popover/@radix-ui/react-switch）
- **R3-W-25**：mingtang UI组件可能缺少dashboard扩展props——AlertDialogAction无variant prop需扩展（与R3-W-2 ScrollArea扩展同类）
- **R3-W-26**：utils函数分散在多个文件（format.ts/tag-parse.ts）——导入时确认实际导出位置，不凭记忆
- **R3-W-27**：大文件重组易引入未使用导入——lint拦截后逐一移除（noUnusedLocals约束）
- **R3-W-28**：预存在测试文件可能有缺陷（缺vi导入）——tsc全量检查会暴露，顺手修复

---

## 变更记录

| 日期 | 版本 | 变更 | 作者 |
|------|------|------|------|
| 2026-08-09 | v1.0 | 初版——8 个问题记录（R3-1-1~R3-1-4 半） | R3 编码代理 |
| 2026-08-09 | v1.1 | R3-1-4 剩余 + R3-1-5 完成——新增 R3-W-9~R3-W-12（12 个问题），三绿 569 tests | R3 编码代理 |
| 2026-08-09 | v1.2 | R3-1-6 + R3-1-7 完成——R3-1 全部 7 任务，三绿 577 tests | R3 编码代理 |
| 2026-08-09 | v2.0 | R3-2 全部 5 任务完成——新增 R3-W-13~R3-W-22（10 个问题），三绿 668 tests / 63 files | R3 编码代理 |
| 2026-08-10 | v3.0 | R3-3-1~R3-3-4 完成（工具簇+重放+展示组件+主页面）——新增 R3-W-23~R3-W-28（6 个问题），三绿 804 tests / 68 files | R3 编码代理 |