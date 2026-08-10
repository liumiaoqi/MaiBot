# R4-1 编码问题记录

> 日期：2026-08-10
> 阶段：R4-1 resource 域 2 页（emoji 精选 + jargon 黑话管理）编码
> 状态：已完成（三绿达成——lint 0 错 + 902 tests 全绿 + build 成功）

---

## 问题 1：set-state-in-effect lint 规则冲突

**现象**：React 19 的 `react-hooks/set-state-in-effect` 规则报错，dashboard 原版两处 useEffect 内调用 setState：
- `multi-select.tsx:54` — `setOpen(false)` 在 disabled 变化时关闭弹出
- `JargonDialogs.tsx:101` — `setFormData(...)` 在 jargon/open 变化时初始化表单

**根因**：React 19 Compiler 禁止 useEffect 内同步 setState（会导致级联渲染）

**修复**：
- `multi-select.tsx` — 改为派生状态：`const open = disabled ? false : openState`，消除 useEffect
- `JargonDialogs.tsx` — 改为 render-time setState 模式：用 `lastJargonId` state 追踪 jargon 变化，在渲染期条件调用 setFormData（React 19 合法模式）

**教训**：从 dashboard 搬移代码时，需检查所有 useEffect 内 setState，适配 React 19 lint 规则

---

## 问题 2：StreamlineIcon 组件缺失

**现象**：dashboard 的 `ChatScopeFilterPanel` 导入 `@/components/ui/streamline-icon`，mingtang 无此组件

**修复**：替换为 `ChevronRight`（lucide-react）直接使用——原代码中 `ChevronRight` 已是 fallback

**影响**：视觉差异极小（StreamlineIcon 是特定图标集，ChevronRight 是通用箭头）

---

## 问题 3：dnd-kit + command 依赖缺失

**现象**：dashboard 的 `MultiSelect` 依赖 `@dnd-kit/core`、`@dnd-kit/sortable`、`@dnd-kit/utilities` 和 `Command` 组件，mingtang 均无

**约束**：R4-1 无新增依赖（design.md §3.6）

**修复**：创建简化版 MultiSelect——用 Popover + Input + Badge 替代 Command + dnd-kit，保留核心多选行为（搜索过滤 + 选择/取消 + 标签展示），去除拖拽排序

**影响**：丢失拖拽排序功能（关联聊天顺序不可拖拽调整）——jargon 创建/编辑对话框的关联聊天多选

**教训**：搬移前需检查目标项目依赖，无新增依赖约束下需做功能裁剪

---

## 问题 4：useToast → sonner toast 适配

**现象**：dashboard 用 `useToast` hook（`@/hooks/use-toast`），mingtang 用 `sonner` 的 `toast`

**修复**：全量替换：
- `toast({ title, description })` → `toast.success(description)`
- `toast({ title, description, variant: 'destructive' })` → `toast.error(description)`
- 动态描述保留三元表达式

**影响**：toast 不再显示 title（仅 description）——sonner 单行 toast 设计

---

## 问题 5：confirmOnEnter prop 缺失

**现象**：dashboard 的 `DialogContent` 有 `confirmOnEnter` prop，mingtang 的 Dialog 无此功能

**修复**：移除 `confirmOnEnter` prop

**影响**：Enter 键不再触发对话框确认——用户需点击确认按钮

---

## 问题 6：加载状态测试——useEffect 同步执行

**现象**：`EmojiCuratedPage` 用 `useEffect` 切换 loading → success 相位，React Testing Library 的 `render()` 同步刷新 effect，loading 态不可测

**修复**：
- 用 `setTimeout(fn, 0)` 延迟相位切换（macrotask 不被 act 同步刷新）
- 组件接受可选 `items` prop（默认 `curatedEmojis`）——测试可注入空数组验证空态

**教训**：静态数据源的加载态是人工的，需用 setTimeout 延迟 + props 注入实现可测性

---

## 问题 7：vi.doMock 对静态导入无效

**现象**：测试中用 `vi.doMock('../curated-emojis', ...)` 模拟空清单，但模块已导入，doMock 不生效

**修复**：改为 props 注入——`<EmojiCuratedPage items={[]} />`

**教训**：静态 import 无法用 vi.doMock 动态替换，需通过 props 注入测试数据

---

## 问题 8：JargonList 双视图导致多元素匹配

**现象**：`JargonList` 同时渲染桌面表格（`hidden md:block`）和移动卡片（`md:hidden`），jsdom 不处理 CSS，两视图均可见，`getByText` 找到多个匹配

**修复**：用 `getAllByText('xxx').length > 0` 替代 `getByText('xxx')`

---

## 问题 9：测试文件扩展名错误

**现象**：`use-data-list.test.ts` 含 JSX（QueryClientProvider wrapper）但用 `.ts` 扩展名，vitest 不解析 JSX → 0 tests

**修复**：重命名为 `.test.tsx`

**教训**：含 JSX 的测试文件必须用 `.tsx` 扩展名

---

## 问题 10：JSX 未转义引号

**现象**：`JargonDialogs.tsx` 中 `确定要删除黑话 "{jargon?.content}" 吗？` 的 `"` 未转义，ESLint `react/no-unescaped-entities` 报错

**修复**：替换为 `&ldquo;` / `&rdquo;`

---

## 问题 11：测试 wrapper 缺少 displayName

**现象**：测试中匿名函数 wrapper `({ children }) => <QueryClientProvider>...` 缺少 displayName，ESLint `react/display-name` 报错

**修复**：提取为命名组件 + `Wrapper.displayName = 'QueryWrapper'`

---

## 总结

| 类别 | 问题数 | 修复策略 |
|------|--------|----------|
| React 19 适配 | 2 | render-time setState / 派生状态 |
| 依赖缺失 | 2 | 简化组件 / 替换图标 |
| API 适配 | 2 | toast 替换 / prop 移除 |
| 测试问题 | 4 | props 注入 / setTimeout / getAllByText / 扩展名 |
| JSX 规范 | 2 | 转义引号 / displayName |

**关键教训**：从 dashboard 搬移到 mingtang 时，需系统性检查：
1. 依赖差异（dnd-kit / command / streamline-icon）
2. React 19 lint 规则（set-state-in-effect）
3. API 差异（useToast → sonner）
4. 测试适配（静态导入 mock / 双视图 / 扩展名）