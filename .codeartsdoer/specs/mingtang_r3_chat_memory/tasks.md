# 明堂前端重写 R3：chat 域 2 页 + memory 域 2 页组装 编码任务清单

> 最后更新：2026-08-09
> 状态：🎨设计 → 📋任务（本文件）
> SSD 阶段：tasks.md（编码任务——"建到什么程度"）
> 版本：v1.0  日期：2026-08-09
> 作者：编码任务规划代理
> 提交标记：[CA]
> 前置：spec.md v1.0 已完成（21 条 EARS 需求 REQ-R3-01~21 + 5 能力模块 + 7 硬决策落实）；design.md v1.0 已完成（9 章 + 8 ADR + 5 PlantUML + 接口/数据模型/测试策略）；R1/R2/TE 已验收通过（build 绿 + 433 tests 绿 + 主题 UI 化完成）；架构蓝皮书已定稿；R3 输入双盘点已完成
> 范围：R3 = chat 域 2 页（/chat + /chat-management）+ memory 域 2 页（/reasoning-process + /resource/knowledge-graph）+ /focus 占位延续（~1.5-2 周）——在 R1/R2/TE 底座上组装聊天与记忆/推理域
> 关键约束：focus 不搬（硬决策 #1）；reasoning-process 三刀切（硬决策 #2）；knowledge-graph 拆分（硬决策 #3）；ws 三件套直接消费（硬决策 #4）；两个孤儿组件补全（硬决策 #5）；乐观更新（硬决策 #6）；纪律沿用（硬决策 #7）；测试先行；蓝皮书一致；不碰 dashboard；[CA]；lint 豁免沿用

---

## 任务总览

| 阶段 | 任务数 | 内容 | 工作量 |
|------|--------|------|--------|
| R3-1 /chat 聊天主界面 | 7 | types/utils + 消息列表（ScrollArea 务实方案）+ 12 段渲染 + 发送+乐观更新 + 标签+侧栏 + 孤儿补全 + 主组件组装 | ~3-4 人日 |
| R3-2 /chat-management 会话档案管理 | 5 | 工具函数+HoverScrollText + 时间轴编辑器 + 五区块 + groups+删除流 + 主组件组装 | ~2-3 人日 |
| R3-3 /reasoning-process 推理过程 | 6 | 工具簇四组抽 lib + 重放子系统 + 推理展示组件 + 主页面+双模式 + 匿名导出+嵌入 + 路由映射 | ~3-4 人日 |
| R3-4 /resource/knowledge-graph 记忆图谱 | 6 | GraphVisualization 整体搬 + GraphDialogs 整体搬 + types + 主组件重组 + 删除闭环+深链 + 路由映射 | ~2-3 人日 |
| R3-5 /focus 占位 + 横切 + 验收 | 3 | /focus 占位 + ws 事件 schema 测试 + 全量回归三绿 | ~1 人日 |
| **总计** | **27** | | **~11-15 人日** |

---

## 全局约束（适用于所有任务）

- **测试先行**：每个实现任务先写配套测试，再写实现（明堂-1 教训：局部当全量 / 测试凑绿都是红旗——R2/TE 沿用）
- **不破坏 R1/R2/TE 已建**：36 页路由 / 注册表 / 搜索 / Layout / lib 搬移 / 三态 / PageShell / 主题 UI 保持不破坏（合法扩展除外：router.tsx 新增 4 页映射 / 注册表确认 chat/memory 域条目）
- **新写法**：React 19.2 / TS 7 新写法基线（R1 W-1~W-8 + TE W-1~W-11 沿用——ref 直接传 / use() / Actions / `<Context>` 当 provider / useRef 永远传参 / useEffect 不传 async / satisfies / as const）
- **纯前端**：后端零改动（方案 A 沿用，复用现有 WS + REST 端点）
- **不兜底**：外部数据返回 None 时不强行 fallback 写入，错误不静默吞（对齐 AGENTS.md debug 规范）
- **简体中文优先**：注释 / 日志 / WebUI 文案
- **i18n 四语言同步**：新文案四个 locale 文件同步加 key，zh 为原文，en / ja / ko 人工翻译不机翻
- **提交标记 [CA]**
- **pnpm 命令**（store E 盘 / allowBuilds 已配）
- **不碰 dashboard/**（旧项目只读——对照基准 + 原版行为来源）
- **lint 全绿**（2026-08-09 更新——原 lint 豁免已废止）：typescript-eslint 已通过 TS 7/6 并存方案恢复（构建用 @typescript/native TS 7 + 工具链用 @typescript/typescript6 TS 6）——`npm run lint` 现为 0 错 0 警验收终点，与 build + test 并列三绿
- **vitest 4 mock 用 vi.hoisted()**（R2 W-1 教训沿用）
- **不全局 mock react-query**（R2 W-2 教训沿用——用真实 QueryClientProvider wrapper）
- **禁止 expect(true).toBe(true) 占位断言**（R2 W-7 教训沿用——测试断言具体行为）
- **edit 工具编辑后 read 验证**（R2 W-6 教训沿用——防首字符破坏）
- **目录结构以蓝皮书为准**（改动位于 features/chat/ + features/memory/ + features/resource/ + features/home/ + app/router.tsx——不一致 = 打回）
- **不提交无边界的格式化 / 导入整理**（AGENTS.md 默认原则 #1 沿用）
- **大文件不搬**：reasoning-process 3415 行三刀切 / knowledge-graph index 1112 行重组 / chat-management 2397 行按切分抓手拆分——不整体搬大文件
- **依赖决策（2026-08-09 确认）**：新增 @xyflow/react（R3-4 图谱画布——原版 reactflow 依赖）+ @radix-ui/react-avatar（头像——与现有 8 个 radix 包一致）；**不装 framer-motion**（原版也不用——动画走 CSS transition + 现有 --animation-* token）；**toast 统一 sonner**（已装——原版 useToast 适配为 sonner，不引入两套）
- **ws 三件套直接消费**：lib/ws 三件套已搬移，页面直接消费不重写 ws 层
- **TE 编码教训沿用**（11 个——spec.md §4.4 #8）：hook 改 Context 测试需包裹 Provider / Partial<T> 非深 Partial / 测试避免 Node.js 模块用 ?raw / Set<字面量联合> 用 Set<string> / spread 不验证接口属性用内联 / HSL 低饱和度色相不稳定

---

## R3-1 /chat 聊天主界面（REQ-R3-01~05）

> 验收目标：WS 消息流 + 多标签 + 虚拟身份 + 运行状态订阅 + 乐观更新 + 两个孤儿组件补全——功能等价于 dashboard 原版
> 输入：dashboard routes/chat/（15 文件 3444 行）+ lib ws 三件套（R1 已搬）+ 13 子组件清单
> 目录：features/chat/

### R3-1-1：types.ts + utils.ts 搬移适配

- [ ] **R3-1-1**
  - **描述**：搬移适配 dashboard routes/chat/types.ts（175 行——ChatTab/MessageSegment 12 型/ChatRuntimeStatus/WsMessage）+ utils.ts（69 行——用户 ID/昵称/头像版本/虚拟标签 localStorage 工具）到 features/chat/
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/types.ts`（ChatTab/MessageSegment/WsMessage/ChatRuntimeStatus——design.md §2.3.2）
    - 新建 `mingtang/src/features/chat/utils.ts`（resolveStatusKind/matchesMonitorTarget/deduplicateMessage + 用户 ID/昵称/头像版本/虚拟标签 localStorage）
    - 新建 `mingtang/src/features/chat/__tests__/chat-types-utils.test.ts`（测试先行）
  - **实现内容**：
    - types.ts：从 dashboard routes/chat/types.ts 搬移类型定义（ChatTab/MessageSegment 12 型/WsMessage 8 类型/ChatRuntimeStatus），统一 PersonInfo 与 lib/person-api.ts 类型（避免重复——spec.md REQ-R3-05 约束）
    - utils.ts：从 dashboard routes/chat/utils.ts 搬移工具函数（用户 ID/昵称/头像版本/虚拟标签 localStorage）+ resolveStatusKind（按 stage 关键词推断 thinking/typing/acting/error）+ matchesMonitorTarget（三级匹配 tab）+ deduplicateMessage（hash 去重上限 100 条）
    - 新写法：TS 7 satisfies / as const
  - **配套测试**（测试先行）：
    - ChatTab 类型正确性 + MessageSegment 12 型 + WsMessage 8 类型
    - resolveStatusKind 各 stage 关键词推断正确
    - matchesMonitorTarget 三级匹配正确
    - deduplicateMessage hash 去重 + 上限 100 条
    - localStorage 工具读写正确
  - **验收条件**：`pnpm run test -- chat-types-utils` 全绿
  - **映射需求**：REQ-R3-01 / REQ-R3-04
  - **依赖关系**：无（首任务——R1/R2 底座已就绪）

---

### R3-1-2：MessageList（ScrollArea + map——务实沿用）+ MessageRenderer 12 段类型

- [ ] **R3-1-2**
  - **描述**：搬移适配 MessageList（原版 290 行——ScrollArea + map，**未虚拟化**——2026-08-09 决策 A 确认：SSD 盘点"564 行虚拟化"有误）+ MessageRenderer（282 行——12 段类型 switch）+ ChatScrollContext（14 行——scrollToMessage 跨组件接口）
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/components/message-list.tsx`（ScrollArea + map 分组渲染/滚动锚点/scrollToMessage 高亮/状态指示三圆点脉冲/空态欢迎页/语音播放行常驻——对齐原版行为等价）
    - 新建 `mingtang/src/features/chat/components/message-renderer.tsx`（12 段类型 switch——text/image/emoji/voice/video/face/music/file/forward/unknown/reply/at——reply 独立块 + scrollToMessage 跳转）
    - 新建 `mingtang/src/features/chat/components/chat-scroll-context.tsx`（scrollToMessage 跨组件接口）
    - 新建 `mingtang/src/features/chat/__tests__/message-list.test.tsx`（测试先行）
    - 新建 `mingtang/src/features/chat/__tests__/message-renderer.test.tsx`（测试先行）
  - **实现内容**：
    - MessageList：ScrollArea + map 分组渲染（对齐原版——不虚拟化；聊天会话消息量场景 ScrollArea 足够，虚拟化引入滚动锚定复杂度不值——如未来消息量暴增再优化渲染层）
    - 消息行渐进增强（2026-08-09 决策）：消息行容器加 `content-visibility: auto` + `contain-intrinsic-size: auto <估算高>`（浏览器原生按需渲染视口外节点——零 JS 复杂度、无需测量高度；不支持的浏览器自动忽略；消息量级将来上来无需换虚拟化库——直接落地，非 TODO）
    - MessageRenderer：12 段类型 switch——reply 段独立块 + scrollToMessage 跳转
    - ChatScrollContext：Context 提供 scrollToMessage
    - 新写法：React 19 Context 直接当 provider
  - **配套测试**（测试先行）：
    - MessageList 分组 + 滚动锚点 + scrollToMessage 高亮 + 空态欢迎页 + 1000 条渲染（ScrollArea 不卡顿——jsdom 渲染断言 + 分组结构）
    - 消息行 content-visibility 规则落地断言（渐进增强——jsdom 无法验证渲染行为，断言消息行容器 class 含 content-visibility 规则对应样式入口）
    - MessageRenderer 12 段类型各渲染正确 + reply 独立块 + scrollToMessage 跳转
    - ChatScrollContext scrollToMessage 跨组件接口
  - **验收条件**：`pnpm run test -- message-list` 全绿 + `pnpm run test -- message-renderer` 全绿
  - **映射需求**：REQ-R3-01
  - **依赖关系**：R3-1-1（types.ts）

---

### R3-1-3：ChatComposer 发送 + UserEmojiManager + 乐观更新

- [ ] **R3-1-3**
  - **描述**：搬移适配 ChatComposer（146 行——自适应 Textarea + 发送按钮 + 图片预览条 + 表情按钮）+ UserEmojiManager（250 行——自定义表情管理 Popover）+ 新建 useOptimisticSend hook（乐观更新三段式——design.md §3.6 / ADR-4）
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/components/chat-composer.tsx`（自适应 Textarea 36-160px + 发送按钮 + 图片预览条 8 张 + 表情按钮 + 未连接态禁用 + Enter 发送 isComposing 保护）
    - 新建 `mingtang/src/features/chat/components/user-emoji-manager.tsx`（自定义表情管理 Popover——add ≤2MB/4 列网格/删除/发送）
    - 新建 `mingtang/src/features/chat/hooks/use-optimistic-send.ts`（乐观更新三段式——onMutate→写入本地→onError 回滚——design.md §3.6.1）
    - 新建 `mingtang/src/features/chat/__tests__/chat-composer.test.tsx`（测试先行）
    - 新建 `mingtang/src/features/chat/__tests__/use-optimistic-send.test.ts`（测试先行——重点）
  - **实现内容**：
    - ChatComposer：自适应 Textarea 36-160px + 发送按钮 + 图片预览条（上限 8 张）+ 表情按钮 + 未连接态禁用 + Enter 发送（isComposing 保护中文输入法）
    - UserEmojiManager：自定义表情管理 Popover——add ≤2MB/4 列网格/删除/发送
    - useOptimisticSend（design.md §3.6.1 / ADR-4）：useMutation onMutate 乐观写入本地消息（即时回显 ≤16ms）+ mutationFn chatWsClient.sendMessage + onError 回滚（移除乐观写入 ≤100ms + 错误提示）
    - 新写法：React 19 Actions / useMutation
  - **配套测试**（测试先行）：
    - ChatComposer 自适应 Textarea + Enter 发送 + isComposing 保护 + 图片 8 张上限 + 未连接态禁用
    - UserEmojiManager add ≤2MB + 4 列网格 + 删除 + 发送
    - **useOptimisticSend 乐观回显 ≤16ms**（核心——onMutate 即时写入本地）
    - **useOptimisticSend 失败回滚 ≤100ms**（核心——onError 移除乐观写入 + 错误提示）
    - **useOptimisticSend 一致性**（不出现"回显但未收到/收到但未回显"——onMutate 总先写入 + onError 回滚）
  - **验收条件**：`pnpm run test -- chat-composer` 全绿 + `pnpm run test -- use-optimistic-send` 全绿
  - **映射需求**：REQ-R3-03 / REQ-R3-20
  - **依赖关系**：R3-1-1（types.ts）+ R3-1-2（MessageList）

---

### R3-1-4：ChatTabBar + ChatWorkspaceSidebar + VirtualIdentityDialog（孤儿补全）

- [ ] **R3-1-4**
  - **描述**：搬移适配 ChatTabBar（144 行——移动端横向会话切换条）+ ChatWorkspaceSidebar（297 行——桌面会话列表 + 用户身份卡）+ VirtualIdentityDialog（224 行——孤儿组件补"新建虚拟会话"入口——design.md ADR-6）
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/components/chat-tab-bar.tsx`（横向会话切换条 + 头像上传）
    - 新建 `mingtang/src/features/chat/components/chat-workspace-sidebar.tsx`（桌面会话列表 + 用户身份卡内联编辑昵称 + **新建虚拟会话入口**——VirtualIdentityDialog 触发按钮）
    - 新建 `mingtang/src/features/chat/components/virtual-identity-dialog.tsx`（身份数据加载 person-api + 创建虚拟会话 + localStorage 持久化）
    - 新建 `mingtang/src/features/chat/__tests__/virtual-identity-dialog.test.tsx`（测试先行）
  - **实现内容**：
    - ChatTabBar：移动端横向会话切换条 + 头像上传
    - ChatWorkspaceSidebar：桌面会话列表 + 用户身份卡内联编辑昵称 + **新建虚拟会话入口**（按钮触发 VirtualIdentityDialog——ADR-6 孤儿补全）
    - VirtualIdentityDialog（ADR-6 孤儿补全）：person-api 加载身份数据源 + 创建虚拟会话 + localStorage 持久化（与 REQ-R3-02 虚拟标签恢复衔接）
    - 新写法：React 19 Context + framer-motion 动画
  - **配套测试**（测试先行）：
    - ChatTabBar 横向标签切换 + 头像上传
    - ChatWorkspaceSidebar 桌面会话列表 + 内联编辑昵称 + 新建虚拟会话入口
    - **VirtualIdentityDialog 孤儿补全**（核心——新建虚拟会话入口 + person-api 加载 + localStorage 持久化）
  - **验收条件**：`pnpm run test -- virtual-identity-dialog` 全绿
  - **映射需求**：REQ-R3-02 / REQ-R3-05
  - **依赖关系**：R3-1-1（types.ts/utils.ts）

---

### R3-1-5：ChatHeaderBar 孤儿复用 + useRuntimeStatus + useChatSession

- [ ] **R3-1-5**
  - **描述**：搬移适配 ChatHeaderBar（127 行——孤儿组件复用到 /chat 页面头部——design.md ADR-6 选项 A）+ 新建 useRuntimeStatus hook（运行状态订阅 5 事件）+ useChatSession hook（WS 会话管理）
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/components/chat-header-bar.tsx`（头像/状态/重连指示——复用到 /chat 头部 + 消费 useRuntimeStatus）
    - 新建 `mingtang/src/features/chat/hooks/use-runtime-status.ts`（maisaka-monitor-client 5 事件订阅 + resolveStatusKind + matchesMonitorTarget）
    - 新建 `mingtang/src/features/chat/hooks/use-chat-session.ts`（chat-ws-client openSession/onSessionMessage + 消息去重 + 连接状态）
    - 新建 `mingtang/src/features/chat/__tests__/chat-header-bar.test.tsx`（测试先行）
    - 新建 `mingtang/src/features/chat/__tests__/use-runtime-status.test.ts`（测试先行）
  - **实现内容**：
    - ChatHeaderBar（ADR-6 选项 A 复用）：头像/状态/重连指示——复用到 /chat 页面头部 + 消费 useRuntimeStatus 衔接运行状态
    - useRuntimeStatus：maisaka-monitor-client 订阅 5 种事件（stage.snapshot/status/removed + llm.retry/error——16 种中子集）+ resolveStatusKind 推断 + matchesMonitorTarget 三级匹配 + 退订 200ms 延迟防 StrictMode 竞态（lib 已实现）
    - useChatSession：chat-ws-client.openSession（幂等/restore）+ onSessionMessage 订阅 + 消息去重（deduplicateMessage）+ 连接状态
    - 新写法：React 19 hooks + lib 直接消费（不重写 ws 层——ADR-3）
  - **配套测试**（测试先行）：
    - ChatHeaderBar 头像/状态/重连指示渲染 + 消费 useRuntimeStatus
    - **useRuntimeStatus 5 事件订阅**（核心——stage.snapshot/status/removed + llm.retry/error）
    - useRuntimeStatus resolveStatusKind 推断 + matchesMonitorTarget 三级匹配
    - useChatSession openSession + onSessionMessage + 消息去重 + 连接状态
  - **验收条件**：`pnpm run test -- chat-header-bar` 全绿 + `pnpm run test -- use-runtime-status` 全绿
  - **映射需求**：REQ-R3-04 / REQ-R3-05 / REQ-R3-19
  - **依赖关系**：R3-1-1（types.ts/utils.ts）

---

### R3-1-6：ChatPage 主组件组装 + ws 直接消费

- [ ] **R3-1-6**
  - **描述**：组装 ChatPage 主组件（index.tsx）——tabs 状态 + activeTabId + WS 消息流订阅 + 运行状态订阅 + 本地身份 + 桌面/移动布局 + framer-motion 动画
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/index.tsx`（ChatPage 主组件——PageShell + 三态 + tabs 状态 + ws 直接消费 + 组件组装）
    - 新建 `mingtang/src/features/chat/__tests__/chat-page.test.tsx`（测试先行）
  - **实现内容**：
    - ChatPage：tabs 状态（ChatTab[]——首个固定 webui-default + 虚拟标签 localStorage 恢复）+ activeTabId + WS 消息流订阅（useChatSession）+ 运行状态订阅（useRuntimeStatus）+ 本地身份（昵称/头像上传 5MB + ?v= 破缓存）
    - 布局：桌面 ChatWorkspaceSidebar + 主区（移动 ChatTabBar + MessageList + ChatComposer）——framer-motion 动画
    - ws 直接消费（ADR-3）：chat-ws-client.openSession/sendMessage/onSessionMessage + maisaka-monitor 5 事件——不重写 ws 层
    - 按蓝皮书 §六 标准骨架：PageShell + 三态齐全 + 数据流 + 组件组装
    - 新写法：React 19 use() / Context
  - **配套测试**（测试先行）：
    - ChatPage 渲染 + tabs 状态 + 首个固定 webui-default
    - **WS 消息流 8 类型**（核心——session_info/system/user_message/bot_message/typing/error/history）
    - **多标签打开/切换/关闭/恢复**（核心——REQ-R3-02）
    - 虚拟标签 localStorage 恢复
    - 桌面/移动布局 + framer-motion 动画
    - ws 直接消费不重写（验证不直接操作 op 信封）
    - 功能等价对照 dashboard
  - **验收条件**：`pnpm run test -- chat-page` 全绿
  - **映射需求**：REQ-R3-01 / REQ-R3-02 / REQ-R3-04
  - **依赖关系**：R3-1-1 + R3-1-2 + R3-1-3 + R3-1-4 + R3-1-5

---

### R3-1-7：router.tsx 新增 /chat 映射

- [ ] **R3-1-7**
  - **描述**：router.tsx actualPageComponents 新增 /chat 映射——ChatPage
  - **涉及文件**：
    - 改造 `mingtang/src/app/router.tsx`（actualPageComponents 新增 '/chat': () => <ChatPage />）
  - **实现内容**：
    - router.tsx actualPageComponents 新增 '/chat' 映射（合法扩展——不破坏 36 页路由）
    - import ChatPage from features/chat
  - **配套测试**：r3-routes.test.tsx（R3-5-2 统一验证）
  - **验收条件**：/chat 路由可达 + 36 页路由不回归
  - **映射需求**：REQ-R3-01
  - **依赖关系**：R3-1-6

---

## R3-2 /chat-management 会话档案管理（REQ-R3-06~09）

> 验收目标：双视图 + 详情弹窗五区块 + groups 视图 + 删除流——功能等价于 dashboard 原版
> 输入：dashboard chat-management.tsx（2397 行）+ lib/chat-management-api（R1 已搬）
> 目录：features/chat/

### R3-2-1：HoverScrollText + 工具函数搬移

- [ ] **R3-2-1**
  - **描述**：搬移适配 HoverScrollText 组件 + chat-management 工具函数（105-198 行）到 features/chat/components/
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/components/hover-scroll-text.tsx`（横向滚动文本组件）
    - 新建 `mingtang/src/features/chat/chat-management-utils.ts`（工具函数——从 dashboard 105-198 行搬移）
  - **实现内容**：
    - HoverScrollText：横向滚动文本组件（按新结构重组）
    - 工具函数：从 dashboard chat-management.tsx 105-198 行搬移
    - 新写法：TS 7 类型注解
  - **配套测试**：chat-management-page.test.tsx（R3-2-5 统一验证）
  - **验收条件**：HoverScrollText 渲染正确
  - **映射需求**：REQ-R3-06
  - **依赖关系**：无

---

### R3-2-2：TalkFrequencyTimelineRule 时间轴编辑器

- [ ] **R3-2-2**
  - **描述**：搬移适配 TalkFrequencyTimelineRule（691 行三层级——24h 拖拽起止 5 分钟步进 + Slider 0-1 + 概览三格 + 生效规则栈）
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/components/talk-frequency-timeline-rule.tsx`（时间轴编辑器——概览三格 + 生效规则栈 + 24h 拖拽起止 5 分钟步进 + Slider 0-1）
    - 新建 `mingtang/src/features/chat/__tests__/talk-frequency-timeline-rule.test.tsx`（测试先行）
  - **实现内容**：
    - TalkFrequencyTimelineRule（691 行三层级——按新结构重组）：概览三格 + 生效规则栈 + 24h 拖拽起止 5 分钟步进 + Slider 0-1
    - 新写法：React 19 drag + Slider
  - **配套测试**（测试先行）：
    - 概览三格渲染 + 生效规则栈
    - 24h 拖拽起止 5 分钟步进
    - Slider 0-1 调整
    - 规则增删改
  - **验收条件**：`pnpm run test -- talk-frequency-timeline-rule` 全绿
  - **映射需求**：REQ-R3-07
  - **依赖关系**：R3-2-1

---

### R3-2-3：详情弹窗五区块组件

- [ ] **R3-2-3**
  - **描述**：搬移适配详情弹窗五区块（基本信息 + 适配器放行 + 频率规则 + Prompt + 学习配置）
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/components/session-detail-dialog.tsx`（详情弹窗——五区块组装）
    - 新建 `mingtang/src/features/chat/components/session-basic-info.tsx`（基本信息——Session ID/Platform/Type/ID）
    - 新建 `mingtang/src/features/chat/components/session-adapters.tsx`（适配器放行——允许/阻止/使用默认）
    - 新建 `mingtang/src/features/chat/components/session-prompts.tsx`（聊天 Prompt——基础只读 + 专属列表增删改 + 变更检测才可保存）
    - 新建 `mingtang/src/features/chat/components/session-learning-config.tsx`（学习配置——表达/黑话/行为三行使用/学习双开关）
  - **实现内容**：
    - 五区块：① 基本信息 ② 适配器放行 ③ 频率规则（TalkFrequencyTimelineRule——R3-2-2）④ Prompt ⑤ 学习配置
    - API：chat-management-api talk-frequency/learning/prompts/adapters（R1 lib 搬移复用）
    - 按蓝皮书 §四 数据流：useQuery + 写操作 invalidateQueries
    - 新写法：React 19 + useQuery
  - **配套测试**：chat-management-page.test.tsx（R3-2-5 统一验证）
  - **验收条件**：五区块完整渲染 + 编辑保存
  - **映射需求**：REQ-R3-07
  - **依赖关系**：R3-2-2

---

### R3-2-4：MutualGroupsView + DeleteChatStreamDialog

- [ ] **R3-2-4**
  - **描述**：搬移适配 MutualGroupsView（1258 行——groups 视图三类共享组）+ DeleteChatStreamDialog（1919 行——严肃确认删除流）
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/components/mutual-groups-view.tsx`（三类共享组——表达/黑话/记忆 + 新建/添加/删除 + 搜索多选 50 条 + 成员徽章）
    - 新建 `mingtang/src/features/chat/components/delete-chat-stream-dialog.tsx`（严肃确认——危险说明框 + 必须输入完整 session_id + 分阶段进度 12→35→82→100% + 明细汇总）
    - 新建 `mingtang/src/features/chat/__tests__/delete-chat-stream-dialog.test.tsx`（测试先行）
  - **实现内容**：
    - MutualGroupsView（1258 行——按新结构重组）：三类共享组（表达/黑话/记忆——URL ?kind=）+ 新建/添加聊天（搜索多选 50 条）/成员徽章/删除整组/全局共享记忆开关禁用态 + 增删即保存整节配置
    - DeleteChatStreamDialog（1919 行——按新结构重组）：危险说明框 + **必须输入完整 session_id 才能启用删除** + 分阶段进度条 12%→35%→82%→100% + 明细汇总
    - 复用 components/biz/ConfirmDialog（蓝皮书 §三——统一危险操作确认出口）
    - API：chat-management-api delete（返回明细——R1 lib 搬移复用）
    - 新写法：React 19 + useMutation + invalidateQueries
  - **配套测试**（测试先行）：
    - MutualGroupsView 三类共享组 + 新建/添加/删除 + 搜索多选 50 条
    - **DeleteChatStreamDialog 严肃确认**（核心——危险说明框 + 必须输入完整 session_id 启用删除）
    - **DeleteChatStreamDialog 分阶段进度 12→35→82→100%**（核心）
    - DeleteChatStreamDialog 明细汇总
  - **验收条件**：`pnpm run test -- delete-chat-stream-dialog` 全绿
  - **映射需求**：REQ-R3-08 / REQ-R3-09
  - **依赖关系**：R3-2-1

---

### R3-2-5：ChatManagementPage 主组件组装 + 路由映射

- [ ] **R3-2-5**
  - **描述**：组装 ChatManagementPage 主组件——双视图 + 头部统计卡 + streams 视图 + groups 视图 + 详情弹窗 + 删除流；router.tsx 新增 /chat-management 映射
  - **涉及文件**：
    - 新建 `mingtang/src/features/chat/chat-management.tsx`（ChatManagementPage——PageShell + 三态 + 双视图 + 组件组装）
    - 改造 `mingtang/src/app/router.tsx`（actualPageComponents 新增 '/chat-management': () => <ChatManagementPage />）
    - 新建 `mingtang/src/features/chat/__tests__/chat-management-page.test.tsx`（测试先行）
  - **实现内容**：
    - ChatManagementPage：双视图（streams/groups——URL ?view= 直达）+ 头部统计卡（全部/群聊/私聊）
    - streams 视图：搜索（12 字段）+ 类型过滤 + DataTable（10 列）+ HoverScrollText + 分页 + 三态
    - groups 视图：MutualGroupsView（R3-2-4）
    - 详情弹窗：五区块（R3-2-3）
    - 删除流：DeleteChatStreamDialog（R3-2-4）
    - 按蓝皮书 §六 标准骨架 + components/biz/DataTable 复用
    - 2397 行按切分抓手拆分（ADR-7）——无 2397 行大文件
    - 新写法：React 19 + useQuery + invalidateQueries
  - **配套测试**（测试先行）：
    - **双视图切换 + URL ?view= 直达**（核心——REQ-R3-06）
    - 头部统计卡（全部/群聊/私聊）
    - streams 视图搜索 12 字段 + 类型过滤 + DataTable 10 列 + 分页 + 三态
    - **五区块完整**（核心——REQ-R3-07）
    - **删除流严肃确认**（核心——REQ-R3-09）
    - 功能等价对照 dashboard
    - 无 2397 行大文件验证
  - **验收条件**：`pnpm run test -- chat-management-page` 全绿 + /chat-management 路由可达
  - **映射需求**：REQ-R3-06 / REQ-R3-07 / REQ-R3-08 / REQ-R3-09
  - **依赖关系**：R3-2-1 + R3-2-2 + R3-2-3 + R3-2-4

---

## R3-3 /reasoning-process 推理过程（REQ-R3-10~13）

> 验收目标：双模式 + 三栏 + 重放子系统 + 匿名导出——三刀切拆分不搬 3415 行大文件
> 输入：dashboard reasoning-process.tsx（3415 行）+ lib/reasoning-process-api（R1 已搬）
> 目录：features/memory/

### R3-3-1：工具簇四组抽 lib（三刀切②）

- [ ] **R3-3-1**
  - **描述**：从 dashboard reasoning-process.tsx 抽出工具簇四组到 features/memory/utils/（三刀切②——design.md ADR-1）
  - **涉及文件**：
    - 新建 `mingtang/src/features/memory/utils/format.ts`（URL 解析/stage 分类行/头部元数据提取——dashboard 204-351 行）
    - 新建 `mingtang/src/features/memory/utils/anonymize.ts`（eraseReasoningNicknames 昵称抹除体系——dashboard 544-697 行）
    - 新建 `mingtang/src/features/memory/utils/tag-parse.ts`（<msg> 标签解析/tool call 归一化/会话显示名——dashboard 787-1094 行）
    - 新建 `mingtang/src/features/memory/utils/replay-prepare.ts`（重放数据准备——dashboard 1502-1644 行）
    - 新建 `mingtang/src/features/memory/__tests__/anonymize.test.ts`（测试先行——重点）
    - 新建 `mingtang/src/features/memory/__tests__/tag-parse.test.ts`（测试先行）
    - 新建 `mingtang/src/features/memory/__tests__/replay-prepare.test.ts`（测试先行）
  - **实现内容**：
    - format.ts：URL 解析（parseReasoningUrl）+ stage 分类行（classifyStageRow）+ 头部元数据提取
    - anonymize.ts：eraseReasoningNicknames 昵称抹除体系（防泄露——spec.md §4.3 安全性）
    - tag-parse.ts：<msg> 标签解析（parseMsgTags）+ tool call 归一化（normalizeToolCalls）+ 会话显示名（getSessionDisplayName）
    - replay-prepare.ts：重放数据准备（prepareReplayData）
    - 新写法：TS 7 纯函数 + 类型注解
  - **配套测试**（测试先行）：
    - format.ts URL 解析 + stage 分类行 + 头部元数据提取
    - **anonymize.ts eraseReasoningNicknames 昵称抹除**（核心——REQ-R3-13）
    - tag-parse.ts <msg> 标签解析 + tool call 归一化 + 会话显示名
    - replay-prepare.ts 重放数据准备
  - **验收条件**：`pnpm run test -- anonymize` 全绿 + `pnpm run test -- tag-parse` 全绿 + `pnpm run test -- replay-prepare` 全绿
  - **映射需求**：REQ-R3-10 / REQ-R3-13
  - **依赖关系**：无

---

### R3-3-2：重放子系统（三刀切①——自包含 ≤650 行）

- [ ] **R3-3-2**
  - **描述**：从 dashboard reasoning-process.tsx 1502-2148 行搬移重放子系统到 features/memory/components/replay/（三刀切①——design.md ADR-1——自包含 ≤650 行只依赖 API + 类型）
  - **涉及文件**：
    - 新建 `mingtang/src/features/memory/components/replay/reasoning-replay-panel.tsx`（重放侧栏 + handleReplay 批量——dashboard 1818-2148 行）
    - 新建 `mingtang/src/features/memory/components/replay/replay-message-editor-column.tsx`（ReplayMessageEditorColumn——dashboard 1644-1752 行）
    - 新建 `mingtang/src/features/memory/components/replay/replay-result-item.tsx`（ReplayResultItem——dashboard 1752-1818 行）
    - 新建 `mingtang/src/features/memory/__tests__/reasoning-replay-panel.test.tsx`（测试先行）
  - **实现内容**：
    - ReasoningReplayPanel：重放侧栏 + handleReplay 批量执行（async + 进度指示——对齐 §4.1 性能 #4 不阻塞 UI）
    - ReplayMessageEditorColumn：重放消息编辑列
    - ReplayResultItem：重放结果展示
    - 重放面板：模型 Select + 温度 + 次数 1-20 批量重放
    - API：reasoning-process-api replay（R1 lib 搬移复用）
    - 自包含（只依赖 API + 类型——最干净切分点）→ features/memory/components/replay/
    - **≤650 行**（对齐 §4.2 可靠性 #9 大文件不搬验证）
    - 新写法：React 19 + useMutation
  - **配套测试**（测试先行）：
    - **重放面板模型 Select + 温度 + 次数 1-20**（核心——REQ-R3-12）
    - **handleReplay 批量执行不阻塞 UI**（核心——async + 进度指示）
    - ReplayResultItem 结果展示
    - 自包含验证（只依赖 API + 类型）
    - **≤650 行验证**（核心——三刀切①）
  - **验收条件**：`pnpm run test -- reasoning-replay-panel` 全绿 + 重放子系统 ≤650 行
  - **映射需求**：REQ-R3-10 / REQ-R3-12
  - **依赖关系**：R3-3-1（replay-prepare.ts）

---

### R3-3-3：推理展示组件

- [ ] **R3-3-3**
  - **描述**：从 dashboard reasoning-process.tsx 搬移推理展示组件到 features/memory/components/
  - **涉及文件**：
    - 新建 `mingtang/src/features/memory/components/llm-error-details.tsx`（LlmErrorDetails——dashboard 351-479 行）
    - 新建 `mingtang/src/features/memory/components/provider-response-timeline.tsx`（ProviderResponseTimeline——dashboard 1196-1389 行）
    - 新建 `mingtang/src/features/memory/components/tool-calls-collapsible.tsx`（ToolCallsCollapsible——dashboard 1133-1196 行）
    - 新建 `mingtang/src/features/memory/components/tool-definitions-collapsible.tsx`（ToolDefinitionsCollapsible——dashboard 1389-1502 行）
    - 新建 `mingtang/src/features/memory/components/natural-language-text.tsx`（NaturalLanguageText——dashboard 1094-1133 行）
  - **实现内容**：
    - 各推理展示组件按 dashboard 行号区间搬移适配
    - 角色样式 + 元数据文本（dashboard 479-544 行）+ jargon_learning_update 专用（dashboard 697-787 行）
    - 新写法：React 19 组件
  - **配套测试**：reasoning-process-page.test.tsx（R3-3-4 统一验证）
  - **验收条件**：各组件渲染正确
  - **映射需求**：REQ-R3-11
  - **依赖关系**：R3-3-1（tag-parse.ts）

---

### R3-3-4：ReasoningProcessPage 主页面 + 双模式（三刀切③）

- [ ] **R3-3-4**
  - **描述**：组装 ReasoningProcessPage 主页面（三刀切③——~35 useState + 副作用链）——双模式 + 三栏 + 内容预览 Tabs
  - **涉及文件**：
    - 新建 `mingtang/src/features/memory/reasoning-process.tsx`（ReasoningProcessPage——三刀切③主页面）
    - 新建 `mingtang/src/features/memory/types.ts`（ReasoningPromptFile/ReplayRequest——design.md §2.3.2）
    - 新建 `mingtang/src/features/memory/__tests__/reasoning-process-page.test.tsx`（测试先行）
  - **实现内容**：
    - ReasoningProcessPage（三刀切③主页面——dashboard 2148-3415 行重组）：~35 useState + 副作用链
    - 双模式：① 类型总览（stage 卡片网格——STAGE_LABELS 13 项 + 会话数 + 最新时间 + hover 清空）② 浏览模式（三栏——记录列表 280px + 内容预览 + 重放面板 420-460px 动画过渡）
    - 记录列表：50 条/页 + 筛选（会话 Select/动作过滤/搜索）
    - 内容预览 Tabs：结构化（LlmErrorDetails/jargon 多轮调用卡/ProviderResponseTimeline/消息流时间线）/文本/HTML（sandbox iframe）
    - 操作：复制/导出/重放
    - API：reasoning-process-api files/stages/clear/getReasoningPromptFile/html（R1 lib 搬移复用）
    - 按蓝皮书 §六 标准骨架
    - **无 2000+ 行文件**（对齐 §4.2 可靠性 #9）
    - 新写法：React 19 + useQuery
  - **配套测试**（测试先行）：
    - **双模式切换**（核心——类型总览 + 浏览模式——REQ-R3-11）
    - **类型总览 13 stage 卡片网格**（核心——STAGE_LABELS 13 项 + 会话数 + 最新时间 + hover 清空）
    - **浏览三栏**（核心——记录列表 280px + 内容预览 + 重放面板 420-460px）
    - 50 条/页 + 筛选
    - 内容预览 Tabs（结构化/文本/HTML sandbox iframe）
    - **三刀切拆分验证**（核心——无 2000+ 行文件）
    - 功能等价对照 dashboard
  - **验收条件**：`pnpm run test -- reasoning-process-page` 全绿 + 无 2000+ 行文件
  - **映射需求**：REQ-R3-10 / REQ-R3-11
  - **依赖关系**：R3-3-1 + R3-3-2 + R3-3-3

---

### R3-3-5：匿名导出 + 嵌入模式

- [ ] **R3-3-5**
  - **描述**：实现匿名导出（抹昵称 Switch + JSON 下载）+ 嵌入模式（createPortal 挂外部容器 + URL 深链）
  - **涉及文件**：
    - 改造 `mingtang/src/features/memory/reasoning-process.tsx`（新增匿名导出 + 嵌入模式）
  - **实现内容**：
    - 匿名导出：抹昵称 Switch（eraseReasoningNicknames 抹去昵称——R3-3-1 anonymize.ts）+ JSON 下载
    - 嵌入模式：createPortal 挂外部容器 + URL 深链（stage/session/stem/returnTo）
    - 新写法：React 19 createPortal
  - **配套测试**：reasoning-process-page.test.tsx 补充用例
  - **验收条件**：匿名导出抹昵称 + JSON 下载 + 嵌入模式 createPortal + URL 深链
  - **映射需求**：REQ-R3-13 / REQ-R3-11
  - **依赖关系**：R3-3-4

---

### R3-3-6：router.tsx 新增 /reasoning-process 映射

- [ ] **R3-3-6**
  - **描述**：router.tsx actualPageComponents 新增 /reasoning-process 映射——ReasoningProcessPage
  - **涉及文件**：
    - 改造 `mingtang/src/app/router.tsx`（actualPageComponents 新增 '/reasoning-process': () => <ReasoningProcessPage />）
  - **实现内容**：
    - router.tsx actualPageComponents 新增 '/reasoning-process' 映射（合法扩展——不破坏 36 页路由）
    - import ReasoningProcessPage from features/memory
  - **配套测试**：r3-routes.test.tsx（R3-5-2 统一验证）
  - **验收条件**：/reasoning-process 路由可达 + 36 页路由不回归
  - **映射需求**：REQ-R3-10
  - **依赖关系**：R3-3-5

---

## R3-4 /resource/knowledge-graph 记忆图谱（REQ-R3-14~17）

> 验收目标：ReactFlow 可视化 + 自研布局 + 删除闭环 + 深链——拆分不搬大文件
> 输入：dashboard resource/knowledge-graph/（2031 行）+ lib/memory-api（R1 已搬）
> 目录：features/resource/

### R3-4-1：GraphVisualization 整体搬（零 API 依赖）

- [ ] **R3-4-1**
  - **描述**：整体搬移 GraphVisualization.tsx（410 行——零 API 依赖纯展示）到 features/resource/components/graph-visualization/（design.md ADR-2）
  - **涉及文件**：
    - 新建 `mingtang/src/features/resource/components/graph-visualization/graph-visualization.tsx`（ReactFlow 画布 + 三种自绘节点 + 自研布局 + 边样式）
    - 新建 `mingtang/src/features/resource/components/graph-visualization/entity-node.tsx`（Entity 蓝节点）
    - 新建 `mingtang/src/features/resource/components/graph-visualization/relation-node.tsx`（Relation 橙节点）
    - 新建 `mingtang/src/features/resource/components/graph-visualization/paragraph-node.tsx`（Paragraph 绿节点）
    - 新建 `mingtang/src/features/resource/components/graph-visualization/layout.ts`（黄金角螺旋 sqrt(index)*radiusScale + 三层锚定证据布局——无 dagre 依赖）
    - 新建 `mingtang/src/features/resource/__tests__/graph-visualization.test.tsx`（测试先行）
  - **实现内容**：
    - GraphVisualization（410 行零 API 依赖——整体搬）：ReactFlow 画布 + 三种自绘节点 + 自研布局 + 边样式
    - 三种自绘节点：Entity 蓝 / Relation 橙 / Paragraph 绿
    - 自研布局：黄金角螺旋（sqrt(index)*radiusScale）+ 三层锚定证据布局——无 dagre 依赖
    - 边样式：kind 配色 / smoothstep / 权重线宽
    - 节点数 ≤500 流畅（对齐 §4.1 性能 #5）
    - 新写法：React 19 + ReactFlow
  - **配套测试**（测试先行）：
    - **ReactFlow 画布渲染**（核心——REQ-R3-15）
    - **三种节点 Entity 蓝/Relation 橙/Paragraph 绿**（核心）
    - **自研布局黄金角螺旋 + 三层锚定**（核心——无 dagre 依赖）
    - 边样式 kind 配色 + smoothstep + 权重线宽
    - ≤500 节点流畅
    - 零 API 依赖验证（纯展示）
  - **验收条件**：`pnpm run test -- graph-visualization` 全绿
  - **映射需求**：REQ-R3-14 / REQ-R3-15
  - **依赖关系**：无

---

### R3-4-2：GraphDialogs 整体搬（四详情 Dialog）

- [ ] **R3-4-2**
  - **描述**：整体搬移 GraphDialogs.tsx（459 行——仅依赖 API 类型）到 features/resource/components/graph-dialogs/（design.md ADR-2）
  - **涉及文件**：
    - 新建 `mingtang/src/features/resource/components/graph-dialogs/graph-dialogs.tsx`（四个详情 Dialog——Node/Edge/Relation/Paragraph）
    - 新建 `mingtang/src/features/resource/__tests__/graph-dialogs.test.tsx`（测试先行）
  - **实现内容**：
    - GraphDialogs（459 行仅依赖 API 类型——整体搬）：四个详情 Dialog（Node/Edge/Relation/Paragraph）
    - API：memory-api node-detail/edge-detail/paragraph-detail（R1 lib 搬移复用）
    - 新写法：React 19 Dialog
  - **配套测试**（测试先行）：
    - **四详情 Dialog Node/Edge/Relation/Paragraph**（核心——REQ-R3-17）
    - 各 Dialog 详情展示正确
    - 仅依赖 API 类型验证
  - **验收条件**：`pnpm run test -- graph-dialogs` 全绿
  - **映射需求**：REQ-R3-14 / REQ-R3-17
  - **依赖关系**：无

---

### R3-4-3：types.ts 搬移

- [ ] **R3-4-3**
  - **描述**：搬移 types.ts（50 行——图数据契约）到 features/resource/types/
  - **涉及文件**：
    - 新建 `mingtang/src/features/resource/types/graph-types.ts`（GraphNode/GraphEdge/DeleteDraft——design.md §2.3.2）
  - **实现内容**：
    - GraphNode（type/id/label/evidence/layoutIndex）+ GraphEdge（kind/source/target/weight/smoothstep）+ DeleteDraft（mode/selector/preview/restorable）
    - 新写法：TS 7 类型注解
  - **配套测试**：knowledge-graph-page.test.tsx（R3-4-4 统一验证）
  - **验收条件**：类型正确性
  - **映射需求**：REQ-R3-14
  - **依赖关系**：无

---

### R3-4-4：KnowledgeGraphPage 主组件重组 + 删除闭环 + 深链

- [ ] **R3-4-4**
  - **描述**：重组 index.tsx 1112 行为 features/resource/knowledge-graph.tsx（状态编排 + 数据转换 + 删除闭环 + 头部 UI）+ 删除闭环 + 深链协议
  - **涉及文件**：
    - 新建 `mingtang/src/features/resource/knowledge-graph.tsx`（KnowledgeGraphPage——主组件重组）
    - 新建 `mingtang/src/features/resource/__tests__/knowledge-graph-page.test.tsx`（测试先行）
  - **实现内容**：
    - KnowledgeGraphPage（index.tsx 1112 行按新结构重组——ADR-2）：状态编排 + 数据转换 + 删除闭环 + 头部 UI
    - 删除闭环：deleteDraft（mode mixed + selector）→ preview → execute → 恢复（restoreGraphTarget 快照恢复选中态）+ 级联清理（删除后自动删"失去全部证据的关系"）
    - 深链协议：embedded + initialParagraphHash（挂载即定位段落——明堂/知识库嵌入页可复用范式）
    - 搜索定位 + 逐级下钻（Node/Edge/Relation/Paragraph 四详情 Dialog——R3-4-2）
    - API：memory-api graph/limit + search + delete 三件套（R1 lib 搬移复用）
    - 按蓝皮书 §四 数据流：useQuery + queryKey `['api', 'memory', 'graph', 参数]`
    - 复用 components/biz/ConfirmDialog（蓝皮书 §三——删除预览确认）
    - **无 1000+ 行文件**（对齐 §4.2 可靠性 #9）
    - 新写法：React 19 + useQuery + useMutation
  - **配套测试**（测试先行）：
    - **搜索定位 + 逐级下钻**（核心——REQ-R3-17）
    - **深链协议 initialParagraphHash**（核心——挂载即定位段落）
    - **删除闭环 deleteDraft → preview → execute → 恢复**（核心——REQ-R3-16）
    - 级联清理（删除后自动删"失去全部证据的关系"）
    - restoreGraphTarget 快照恢复选中态
    - **无 1000+ 行文件验证**（核心——拆分）
    - 功能等价对照 dashboard
  - **验收条件**：`pnpm run test -- knowledge-graph-page` 全绿 + 无 1000+ 行文件
  - **映射需求**：REQ-R3-14 / REQ-R3-16 / REQ-R3-17
  - **依赖关系**：R3-4-1 + R3-4-2 + R3-4-3

---

### R3-4-5：router.tsx 新增 /resource/knowledge-graph 映射

- [ ] **R3-4-5**
  - **描述**：router.tsx actualPageComponents 新增 /resource/knowledge-graph 映射——KnowledgeGraphPage
  - **涉及文件**：
    - 改造 `mingtang/src/app/router.tsx`（actualPageComponents 新增 '/resource/knowledge-graph': () => <KnowledgeGraphPage />）
  - **实现内容**：
    - router.tsx actualPageComponents 新增 '/resource/knowledge-graph' 映射（合法扩展——不破坏 36 页路由）
    - import KnowledgeGraphPage from features/resource
  - **配套测试**：r3-routes.test.tsx（R3-5-2 统一验证）
  - **验收条件**：/resource/knowledge-graph 路由可达 + 36 页路由不回归
  - **映射需求**：REQ-R3-14
  - **依赖关系**：R3-4-4

---

### R3-4-6：注册表确认 knowledge-graph 域条目

- [ ] **R3-4-6**
  - **描述**：确认 settings-registry chat/memory 域条目完整（R1 已登记——R3 确认不缺）
  - **涉及文件**：
    - 检查 `mingtang/src/settings-registry/` manual 登记含 chat/memory 域菜单项
  - **实现内容**：
    - 确认注册表 chat/memory 域条目完整（合法扩展——不破坏已有登记）
    - 如有缺失则补充
  - **配套测试**：r3-routes.test.tsx（R3-5-2 统一验证）
  - **验收条件**：注册表 chat/memory 域条目完整
  - **映射需求**：REQ-R3-21
  - **依赖关系**：R3-4-5

---

## R3-5 /focus 占位 + 横切 + 验收（REQ-R3-18~21）

> 验收目标：/focus 占位延续 + ws 事件 schema 测试 + 全量回归三绿
> 目录：features/home/ + lib/ + app/

### R3-5-1：/focus 占位延续

- [ ] **R3-5-1**
  - **描述**：新建 /focus 占位页（如 R2 model-presets 模式——标题 + 虚线卡片"功能开发中" + 即将推出列表）+ router.tsx 新增 /focus 映射
  - **涉及文件**：
    - 新建 `mingtang/src/features/home/focus.tsx`（占位页——如 model-presets 模式）
    - 改造 `mingtang/src/app/router.tsx`（actualPageComponents 新增 '/focus': () => <FocusPage />）
  - **实现内容**：
    - FocusPage 占位（ADR-5——如 R2 model-presets 模式）：标题 + 虚线卡片"功能开发中" + 即将推出列表
    - 不引入 three.js / @pixiv/three-vrm 依赖
    - 路由可达（R1 已登记，R3 组装占位本体）
    - 新写法：React 19 + PageShell
  - **配套测试**：r3-routes.test.tsx（R3-5-2 统一验证）
  - **验收条件**：/focus 占位渲染 + 路由可达 + 无 3D/VRM 依赖
  - **映射需求**：REQ-R3-18
  - **依赖关系**：无

---

### R3-5-2：ws 事件 schema 测试 + r3-routes 测试

- [ ] **R3-5-2**
  - **描述**：新建 ws 事件 schema 测试（zulip 调研沿用——design.md §3.7）+ r3-routes 测试（4 页路由可达 + 36 页不回归）
  - **涉及文件**：
    - 新建 `mingtang/src/lib/__tests__/ws-event-schema.test.ts`（ws 事件 schema 校验——zulip 调研沿用）
    - 新建 `mingtang/src/app/__tests__/r3-routes.test.tsx`（4 页路由可达 + 36 页不回归）
  - **实现内容**：
    - ws-event-schema.test.ts：每个 ws 事件 payload schema 校验（session_info/user_message/bot_message/typing/error/history/system + stage.snapshot/status/removed + llm.retry/error——design.md §3.7）
    - r3-routes.test.tsx：4 页路由可达（/chat + /chat-management + /reasoning-process + /resource/knowledge-graph）+ 36 页路由不回归 + /focus 占位渲染
    - 新写法：vitest 4 + vi.hoisted()
  - **配套测试**（测试先行）：
    - **ws 事件 schema 校验**（核心——REQ-R3-19——zulip 调研沿用防事件格式静默回归）
    - **4 页路由可达**（核心——/chat + /chat-management + /reasoning-process + /resource/knowledge-graph）
    - **36 页路由不回归**（核心——R1/R2/TE 已建 36 页全部可达）
    - /focus 占位渲染 + 无 3D/VRM 依赖
  - **验收条件**：`pnpm run test -- ws-event-schema` 全绿 + `pnpm run test -- r3-routes` 全绿
  - **映射需求**：REQ-R3-19 / REQ-R3-21
  - **依赖关系**：R3-1-7 + R3-2-5 + R3-3-6 + R3-4-5 + R3-5-1

---

### R3-5-3：全量回归三绿（build + test 全绿 + 数量增长 + 蓝皮书一致）

- [ ] **R3-5-3**
  - **描述**：全量回归验证——build 绿 + test 全绿 + 测试数量相对 TE 的 433 增长 + 蓝皮书一致 + 大文件不搬验证
  - **涉及文件**：
    - 运行 `pnpm run build`（build 绿验证）
    - 运行 `pnpm run test`（test 全绿 + 数量增长验证）
    - 运行 `pnpm run lint`（lint 全量绿——2026-08-09 TS 7/6 并存方案恢复，0 错 0 警）
    - 验证大文件不搬（reasoning-process 无 2000+ 行 + knowledge-graph 无 1000+ 行 + chat-management 无 2397 行）
    - 验证蓝皮书一致（目录/组件/数据流/导航/页面模板）
  - **实现内容**：
    - build 绿：`pnpm run build` 通过（沿用 R1/R2/TE 基线）
    - test 绿：`pnpm run test` 全绿，测试数量相对 TE 的 433 增长（chat 域 2 页 + memory 域 2 页 + ws 消息处理 + 重放 + 图谱交互 + 乐观更新配套测试）
    - lint 全量绿：`pnpm run lint` 0 错 0 警（2026-08-09 TS 7/6 并存方案恢复——typescript-eslint 8.66 通过 TS 6.0.3 满足 peer）
    - 大文件不搬验证：reasoning-process 无 2000+ 行（三刀切后重放子系统 ≤650 行 + 工具簇抽 lib + 主页面 ≤合理行数）；knowledge-graph index 重组后无 1000+ 行；chat-management 无 2397 行
    - 蓝皮书一致：目录/组件/数据流/导航/页面模板对照蓝皮书定稿
    - 36 页路由不回归：R1/R2/TE 已建的 36 页路由全部保持可达
    - 后端零改动：`git diff src/webui/` 为空（纯前端方案 A 沿用）
  - **配套测试**：全量 test 套件
  - **验收条件**：
    - `pnpm run build` 绿
    - `pnpm run test` 全绿 + 数量 > 433
    - `pnpm run lint` 0 错 0 警（全量绿）
    - 大文件不搬验证通过
    - 蓝皮书一致验证通过
    - 36 页路由不回归验证通过
    - 后端零改动验证通过
  - **映射需求**：REQ-R3-21
  - **依赖关系**：R3-5-2（所有任务完成后）

---

## 任务依赖关系图

```plantuml
@startuml
!theme plain
skinparam componentStyle rectangle

' R3-1 /chat
rectangle "R3-1-1\ntypes+utils" as R311
rectangle "R3-1-2\nMessageList\n+MessageRenderer" as R312
rectangle "R3-1-3\nChatComposer\n+乐观更新" as R313
rectangle "R3-1-4\nTabBar+Sidebar\n+VirtualIdentity" as R314
rectangle "R3-1-5\nChatHeaderBar\n+hooks" as R315
rectangle "R3-1-6\nChatPage\n主组件" as R316
rectangle "R3-1-7\nrouter /chat" as R317

' R3-2 /chat-management
rectangle "R3-2-1\nHoverScroll\n+工具函数" as R321
rectangle "R3-2-2\n时间轴\n编辑器" as R322
rectangle "R3-2-3\n五区块" as R323
rectangle "R3-2-4\ngroups\n+删除流" as R324
rectangle "R3-2-5\nChatMgmtPage\n+router" as R325

' R3-3 /reasoning-process
rectangle "R3-3-1\n工具簇四组\n(三刀切②)" as R331
rectangle "R3-3-2\n重放子系统\n(三刀切①)" as R332
rectangle "R3-3-3\n推理展示\n组件" as R333
rectangle "R3-3-4\n主页面\n(三刀切③)" as R334
rectangle "R3-3-5\n匿名导出\n+嵌入" as R335
rectangle "R3-3-6\nrouter" as R336

' R3-4 /resource/knowledge-graph
rectangle "R3-4-1\nGraphViz\n整体搬" as R341
rectangle "R3-4-2\nGraphDialogs\n整体搬" as R342
rectangle "R3-4-3\ntypes" as R343
rectangle "R3-4-4\n主组件重组\n+删除闭环" as R344
rectangle "R3-4-5\nrouter" as R345
rectangle "R3-4-6\n注册表" as R346

' R3-5 /focus + 横切
rectangle "R3-5-1\n/focus占位" as R351
rectangle "R3-5-2\nws schema\n+r3-routes" as R352
rectangle "R3-5-3\n全量回归\n三绿" as R353

' 依赖关系
R311 --> R312
R311 --> R313
R311 -->F R314
R311 --> R315
R312 --> R313
R311 --> R316
R312 --> R316
R313 --> R316
R314 --> R316
R315 --> R316
R316 --> R317

R321 --> R322
R322 -->323
R321 --> R324
R321 --> R325
R322 --> R325
R323 --> R325
R324 --> R325

R331 --> R332
R331 --> R333
R332 --> R334
R333 --> R334
R331 --> R334
R334 --> R335
R335 --> R336

R341 --> R344
R342 --> R344
R343 --> R344
R344 --> R345
R345 --> R346

R317 --> R352
R325 --> R352
R336 --> R352
R345 --> R352
R351 --> R352
R352 --> R353

@enduml
```

---

## 验收标准映射总览

| 需求 | 验收条件 | 任务 |
|------|---------|------|
| REQ-R3-01 WS 消息流 | 8 类型渲染 + 消息列表（ScrollArea 务实方案——2026-08-09 决策 A）+ 12 段类型 + 去重 + history 1000 条 + ws 直接消费 | R3-1-1 + R3-1-2 + R3-1-6 |
| REQ-R3-02 多标签 | 打开/切换/关闭/恢复 + 首个固定 webui-default + 虚拟标签 localStorage | R3-1-4 + R3-1-6 |
| REQ-R3-03 发送+乐观更新 | ChatComposer + Enter 发送 + 图片 8 张 + 乐观回显 ≤16ms + 失败回滚 ≤100ms | R3-1-3 |
| REQ-R3-04 身份+运行状态 | 昵称/头像 5MB + 5 事件订阅 + resolveStatusKind + matchesMonitorTarget + 三圆点脉冲 | R3-1-5 |
| REQ-R3-05 孤儿补全 | ChatHeaderBar 复用 + VirtualIdentityDialog 补入口 + person-api + localStorage | R3-1-4 + R3-1-5 |
| REQ-R3-06 双视图 | 双视图 + URL ?view= + 统计卡 + streams 搜索/过滤/数据表/分页 | R3-2-5 |
| REQ-R3-07 五区块 | 五区块完整 + 适配器 + 频率时间轴 + Prompt 增删改 + 学习双开关 | R3-2-2 + R3-2-3 + R3-2-5 |
| REQ-R3-08 groups | 三类共享组 + 新建/添加/删除 + 搜索多选 50 条 | R3-2-4 + R3-2-5 |
| REQ-R3-09 删除流 | 严肃确认 + 输入 session_id 启用 + 分阶段进度 + 明细汇总 | R3-2-4 + R3-2-5 |
| REQ-R3-10 三刀切 | 三刀切拆分 + 重放 ≤650 行 + 无 2000+ 行文件 | R3-3-1 + R3-3-2 + R3-3-4 |
| REQ-R3-11 双模式 | 类型总览 13 stage + 浏览三栏 + 50 条/页 + 筛选 + 嵌入模式 | R3-3-3 + R3-3-4 + R3-3-5 |
| REQ-R3-12 重放 | 模型/温度/次数 1-20 + 批量不阻塞 + 结果展示 + 自包含切分 | R3-3-2 |
| REQ-R3-13 匿名导出 | 抹昵称 Switch + JSON 下载 + 昵称抹除 | R3-3-1 + R3-3-5 |
| REQ-R3-14 拆分 | GraphVisualization 整体搬 + GraphDialogs 整体搬 + 无 1000+ 行 | R3-4-1 + R3-4-2 + R3-4-3 + R3-4-4 |
| REQ-R3-15 ReactFlow | ReactFlow + 三节点 + 自研布局 + 边样式 + ≤500 节点 | R3-4-1 |
| REQ-R3-16 删除闭环 | deleteDraft → preview → execute → 恢复 + 级联清理 | R3-4-4 |
| REQ-R3-17 搜索+深链 | 搜索 + 逐级下钻 + 四 Dialog + initialParagraphHash | R3-4-2 + R3-4-4 |
| REQ-R3-18 /focus 占位 | 占位渲染 + 路由可达 + 无 3D/VRM 依赖 | R3-5-1 |
| REQ-R3-19 ws 直接消费 | ws 三件套直接消费 + 事件 schema 测试 | R3-1-5 + R3-5-2 |
| REQ-R3-20 乐观更新 | 即时回显 ≤16ms + 失败回滚 ≤100ms + 一致性 + 低频用失效刷新 | R3-1-3 |
| REQ-R3-21 横切纪律 | 大文件不搬 + 测试先行 + 蓝皮书一致 + 36 页不回归 | R3-5-2 + R3-5-3 |

---

## 风险映射

| 任务 | 风险 # | 风险描述 | 缓解措施 | 阶段 |
|------|--------|---------|---------|------|
| R3-1-3 | R-2 | 乐观更新一致性失效 | onMutate 总先写入 + onError 回滚 + use-optimistic-send.test.ts 一致性测试 | R3-1 |
| R3-1-5 | R-1 | ws 三件套契约不匹配 | R1 已搬移测试通过 + ws-event-schema.test.ts 事件 schema 校验 | R3-1 |
| R3-1-4 | R-5 | 孤儿组件补全引入新 bug | ChatHeaderBar 复用（不重写）+ VirtualIdentityDialog 补入口（不重写） | R3-1 |
| R3-2-5 | R-7 | chat-management 2397 行拆分遗漏 | 按切分抓手拆分 + dashboard 只读对照 + chat-management-page.test.tsx 功能等价 | R3-2 |
| R3-3-4 | R-3 | 三刀切拆分遗漏原版功能 | dashboard 只读对照 + reasoning-process-page.test.tsx 功能等价 + 无 2000+ 行验证 | R3-3 |
| R3-4-4 | R-4 | knowledge-graph 重组状态编排错误 | GraphVisualization/GraphDialogs 整体搬（行为等价）+ index 重组对照 dashboard | R3-4 |
| R3-5-2 | R-6 | 36 页路由回归 | r3-routes.test.tsx 36 页路由不回归测试 + router.tsx 只新增映射不删 | R3-5 |
| 全程 | R-7 | 大文件搬移违规 | 三刀切 + 拆分 + 切分抓手 + 代码审查打回 | 全程 |
| 全程 | R-8 | 测试未先行 | 每任务配套测试先行编写 + 代码审查打回（明堂-1 教训） | 全程 |
| 全程 | R-9 | TE 编码教训重犯 | 11 个教训沿用 + 测试约束 §全局约束 | 全程 |
| 全程 | R-10 | 蓝皮书不一致 | 目录/组件/数据流/导航对照蓝皮书 + 不一致 = 打回 | 全程 |

---

## 边界防蔓延（对齐 R2 模式）

| # | 边界 | 理由 | 任务落实 |
|---|------|------|---------|
| 1 | 不碰 dashboard/ | 只读对照基准（spec.md §1.4 #2） | 全程只读 |
| 2 | 不做后端改动 | 纯前端方案 A 沿用（spec.md §1.4 #4） | 全程 `git diff src/webui/` 为空 |
| 3 | 不重写 ws 层 | lib 直接消费（spec.md §1.4 #5——硬决策 #4） | R3-1-5 + R3-1-6 直接消费 lib |
| 4 | 不搬 focus.tsx | 用户拍板不搬（spec.md §1.4 #6——硬决策 #1） | R3-5-1 占位延续 |
| 5 | 不搬大文件 | 三刀切 + 拆分 + 切分抓手（spec.md §1.4 #3） | R3-3 三刀切 + R3-4 拆分 + R3-2 切分 |
| 6 | 不破坏 R1/R2/TE 已建 | 36 页路由/注册表/搜索/Layout/lib/三态/PageShell/主题 UI（spec.md §1.4 #7） | R3-5-2 + R3-5-3 回归验证 |
| 7 | 不做 R4 页面组装 | R3 仅组装 chat/memory 4 页（spec.md §1.4 #1） | R3 范围仅 chat/memory |
| 8 | 不做新旧并行切换 | R3 仅组装（spec.md §1.4 #8） | R5 质量批次 |
| 9 | 不做 ConfirmDialog 本体 | R3 复用 R1 已建（spec.md §1.4 #10） | R3-2-4 + R3-4-4 复用 |
| 10 | lint 全绿 | 2026-08-09 更新（TS 7/6 并存方案恢复 typescript-eslint） | npm run lint 0 错 0 警 + build + test 三绿 |

---

## 引用

| # | 引用 | 用途 |
|---|------|------|
| 1 | spec.md（本目录） | 21 条 EARS 需求 + 5 能力模块 + 7 硬决策 |
| 2 | design.md（本目录） | 9 章 + 8 ADR + 5 PlantUML + 接口/数据模型/测试策略 |
| 3 | `.shared/decisions/WebUI_Plan/mingtang_architecture_blueprint_0808.md` | 架构蓝皮书（R1-R4 总纲） |
| 4 | `.shared/decisions/WebUI_Plan/mingtang_r3_chat_inventory_0809.md` | chat 域功能点盘点 |
| 5 | `.shared/decisions/WebUI_Plan/mingtang_r3_memory_inventory_0809.md` | memory 域功能点盘点 |
| 6 | `.shared/handoff/cc2ca_mingtang_r3_ssd_0809.md` | CC 交接（R3 范围 + 硬决策 + 验收） |
| 7 | `.shared/handoff/cc2ca_mingtang_r1_notes_0808.md` | R1 编码注意点（lint 豁免 + 视觉需求 + 搬移纪律） |
| 8 | `.shared/decisions/typescript_new_code_cheatsheet.md` | TS 速查（React 19.2 + TS 7 新写法） |
| 9 | `.shared/research/2026-08/zulip_arch_0807.md` | zulip ws 事件 schema 测试制度 |
| 10 | `.codeartsdoer/specs/mingtang_theme_enhance/te_coding_issues.md` | TE 编码问题记录（11 个教训） |
| 11 | `.codeartsdoer/specs/mingtang_theme_enhance/tasks.md` | TE tasks.md（格式与粒度对齐基准） |
| 12 | `.codeartsdoer/specs/mingtang_r2_config_domain/tasks.md` | R2 tasks.md（格式与粒度对齐基准） |
| 13 | dashboard/src/routes/chat/ | chat 域原版（只读对照基准） |
| 14 | dashboard/src/routes/reasoning-process.tsx | reasoning-process 原版（三刀切参考） |
| 15 | dashboard/src/routes/resource/knowledge-graph/ | knowledge-graph 原版（拆分参考） |

---

## 变更记录

| 日期 | 版本 | 变更 | 作者 |
|------|------|------|------|
| 2026-08-09 | v1.0 | 初版——27 任务 / 5 阶段 / 测试先行 / 验收映射 / 风险映射 / 边界防蔓延 | 编码任务规划代理 |