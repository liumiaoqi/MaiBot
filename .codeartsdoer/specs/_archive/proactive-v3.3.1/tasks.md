# proactive-chat v3.3.1 编码任务

> 任务编号从 268 开始（v3.3 任务编号为 241-267，已完成）

---

## 1. 配置页修复

### #268 loadConfig() 重构为动态分组渲染

- [ ] 重写 `loadConfig()` 函数，将硬编码的 `sections` 对象替换为动态遍历配置 API 返回的所有顶层键
  - 删除硬编码的 `sections` 对象（仅含 12 个固定分组键）
  - 新增 `SECTION_TITLES` 常量：包含所有已知分组键到中文标题的映射（plugin→插件、trigger→触发、cooldown→冷却、analysis→分析、deepseek→DeepSeek、scope→白名单、prompt→提示词、webui→WebUI、smart_cleanup→智能清理、status→状态、delayed_trigger→延迟触发、react→ReAct 循环、context_compress→上下文压缩、deepseek_context→1M 上下文、agent_chat→智能体对话、deepseek_v4→DeepSeek v4、agent_memory→智能体记忆、deepseek_optimization→DeepSeek 优化、agent_optimization→智能体优化）
  - 新增 `renderConfigSection(sectionKey, title, data)` 函数：渲染单个配置分组，为每个分组添加 `id="config-section-{key}"` 便于锚点跳转
  - `loadConfig()` 中使用 `Object.keys(d)` 动态获取分组键，跳过非对象值（`typeof !== 'object' || === null`），用 `SECTION_TITLES[key] || key` 获取标题
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：无
  - 验收标准：配置 API 返回包含 `agent_chat`、`agent_optimization`、`delayed_trigger` 等分组 → 配置页面自动显示这些分组及其中所有字段；后端新增任意配置分组 → 前端自动显示，无需修改代码

### #269 renderConfigField() 修复布尔/数值/密码/数组字段交互

- [ ] 新增 `renderConfigField(sectionKey, fieldKey, fieldValue)` 函数，替代 `loadConfig()` 中内联的字段渲染逻辑
  - 布尔字段：使用 `type="checkbox"`，`checked` 属性仅在 `fieldValue === true` 时添加，不设置 `value` 属性
  - 数值字段：使用 `type="number"`，`value` 直接赋值为 `fieldValue`（不再通过 `typeof fv==='boolean'?'':fv` 三元表达式）
  - 密码字段：`fieldKey === 'deepseek_api_key'` 时使用 `type="password"`，添加 `placeholder="已脱敏，留空则保留原值"` 提示
  - 数组字段：`Array.isArray(fieldValue)` 时使用 `type="text"` + `data-type="array"`，显示值用 `fieldValue.join(', ')`
  - 文本字段：默认使用 `type="text"`，`value` 用 `escapeAttr(String(fieldValue ?? ''))` 转义
  - 每个字段后添加 `<span class="config-error" id="error-{fullKey}"></span>` 用于字段级错误提示
  - 新增 `escapeAttr(str)` 工具函数：转义 `&`、`"`、`'`、`<`、`>` 用于 HTML 属性值
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#268
  - 验收标准：布尔字段 `true` → 复选框勾选，`false` → 未勾选；数值字段 0 → 显示 0；密码字段显示为密码输入框；数组字段显示为逗号分隔文本；保存时正确传递各类型值

### #270 saveConfig() 优化为增量保存 + 字段级错误反馈

- [ ] 重写 `saveConfig()` 函数，优化保存逻辑和错误反馈
  - 布尔字段：读取 `el.checked`（布尔值）
  - 数值字段：`parseFloat(el.value)`，`NaN` 时不提交该字段（保留原值）
  - 数组字段：`el.value.split(',').map(s=>s.trim()).filter(s=>s)` 按逗号分隔
  - 密码字段：空值时不提交（保留原值），非空时提交
  - 保存前清除所有 `.config-error` 的文本内容
  - 保存成功时：显示成功 Toast，调用 `fetchJSON` 重新获取配置，调用 `updateConfigValues(newConfig)` 平滑更新输入框值（不重建 DOM）
  - 保存失败时：显示失败 Toast，调用 `showConfigErrors(r.error)` 在配置区域顶部显示完整错误信息
  - 新增 `updateConfigValues(config)` 函数：遍历 `.config-input`，根据 `config[sec][field]` 更新 `el.checked`/`el.value`，不重建 DOM
  - 新增 `showConfigErrors(errorMessage)` 函数：在 `config-content` 顶部插入 `.config-global-error` 元素，显示错误详情
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#269
  - 验收标准：保存成功 → Toast 提示 + 输入框值平滑更新（无页面闪烁）；保存失败 → Toast 提示 + 配置区域顶部显示错误详情 + 用户已编辑内容不丢失

### #271 配置分组导航栏

- [ ] 在配置页面新增分组导航栏，支持锚点跳转
  - 在 `index.html` 的 `tab-config` 内、`config-content` 前新增 `<div id="config-nav" class="config-nav" style="display:none"></div>`
  - 新增 `renderConfigNav(sectionKeys)` 函数：分组数 ≤6 时隐藏导航，>6 时显示导航按钮（使用 `SECTION_TITLES[key] || key` 作为按钮文本）
  - 新增 `scrollToConfigSection(key)` 函数：调用 `document.getElementById('config-section-'+key).scrollIntoView({behavior:'smooth',block:'start'})`
  - 在 `loadConfig()` 末尾调用 `renderConfigNav(sectionKeys)`
  - 在 `style.css` 中新增 `.config-nav` 和 `.config-nav-btn` 样式：flex wrap 布局、sticky top、圆角按钮、hover 变色
  - 涉及文件：`webui_static/app.js`、`webui_static/index.html`、`webui_static/style.css`
  - 依赖任务：#268
  - 验收标准：配置页面包含 15+ 分组时 → 顶部显示分组导航栏，点击按钮平滑滚动到对应分组；分组 ≤6 时导航栏隐藏

---

## 2. 智能体对话修复

### #272 会话消息本地缓存

- [ ] 引入 `chatMessageCache`（`Map<session_id, Message[]>`），修复会话切换消息丢失
  - 新增全局变量：`const chatMessageCache = new Map()`、`const MAX_MESSAGES_PER_SESSION = 100`
  - 重写 `selectChatSession(sid)`：
    1. 保存当前会话消息到缓存：`if (currentChatSessionId && currentChatMessages.length > 0) chatMessageCache.set(currentChatSessionId, [...currentChatMessages])`
    2. 切换到目标会话：`currentChatSessionId = sid`
    3. 从缓存恢复目标会话消息：`currentChatMessages = chatMessageCache.has(sid) ? [...chatMessageCache.get(sid)] : []`
    4. 渲染消息和更新会话信息栏
  - 修改 `sendAgentChatMessage()`：每次消息添加到 `currentChatMessages` 后同步更新缓存 `chatMessageCache.set(currentChatSessionId, [...currentChatMessages])`
  - 修改 `clearAgentChatSession()`：清除成功后 `chatMessageCache.delete(currentChatSessionId)`
  - 新增 `trimCacheMessages(sessionId)` 函数：缓存超过 100 条时截断为最近 100 条
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：无
  - 验收标准：会话 A 有 3 条消息 → 切换到会话 B → 切换回会话 A → 显示 3 条消息；会话 A 和 B 的消息互不干扰

### #273 聊天流显示名称

- [ ] 会话列表和会话信息栏使用 `display_name` 替代截断的 session_id
  - 新增全局变量：`let streamDisplayMap = new Map()`
  - 新增 `loadStreamDisplayMap()` 函数：GET `/api/proactive-chat/streams`，构建 `stream_id → {display_name, chat_type}` 映射
  - 修改 `loadAgentChat()`：先调用 `await loadStreamDisplayMap()`，再调用 `await loadAgentChatSessions()`
  - 重写 `renderSessionList()`：
    - 按最后活跃时间倒序排列：`sorted = [...agentChatSessions].sort((a,b) => (b.last_active_at||0) - (a.last_active_at||0))`
    - 聊天流显示名称：从 `streamDisplayMap` 获取，群聊显示 `[群聊] 群名称`，私聊显示 `[私聊] 昵称的私聊`；映射不到时 fallback 为截断 ID
    - 会话项显示：聊天流名称（或截断 ID）+ 时间 + 消息数
  - 新增 `updateChatSessionInfo(sid)` 函数：显示会话 ID + 关联聊天流名称 + 消息数量，用 `·` 分隔
  - 在 `selectChatSession()` 中调用 `updateChatSessionInfo(sid)`
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：无
  - 验收标准：会话关联聊天流"测试群" → 会话列表和会话信息栏显示"关联: [群聊] 测试群"；未关联聊天流 → 不显示关联信息；聊天流列表获取失败 → fallback 为截断 ID

### #274 思考状态动画指示器

- [ ] 将文本"思考中..."替换为带 CSS 动画的脉冲点指示器
  - 新增 `showThinkingIndicator()` 函数：动态创建 `.thinking-indicator` 元素（含 3 个 `.thinking-dot` + "思考中"文本），插入到 `chat-messages` 末尾，自动滚动到底部
  - 新增 `removeThinkingIndicator()` 函数：移除 `#thinking-indicator` 元素
  - 修改 `sendAgentChatMessage()`：发送消息后调用 `showThinkingIndicator()` 替代当前的 `thinking.textContent='思考中...'`；收到响应后调用 `removeThinkingIndicator()`
  - 在 `style.css` 中新增样式：
    - `.thinking-indicator`：flex 布局、圆角气泡、左侧对齐
    - `.thinking-dots`：flex + gap
    - `.thinking-dot`：6px 圆点、accent 背景、`thinkingBounce` 动画
    - `@keyframes thinkingBounce`：0%/60%/100% → translateY(0) + opacity 0.4；30% → translateY(-6px) + opacity 1
    - 第 2、3 个 dot 分别延迟 0.15s、0.3s
  - 删除旧的 `.thinking-indicator` 样式（仅 `color` + `font-size` + `padding` 的简单文本样式）
  - 涉及文件：`webui_static/app.js`、`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：消息发送后 → 对话区域显示带动画的脉冲点指示器 + "思考中"文本；收到响应后 → 指示器消失，显示实际回复内容

### #275 空会话提示

- [ ] 新建会话后消息区域显示友好的空状态提示
  - 修改 `renderChatMessages()`：当 `currentChatMessages.length === 0` 时，显示 `<div class="chat-empty-hint">开始与智能体对话 ✨</div>`，替代空白区域
  - 在 `style.css` 中新增 `.chat-empty-hint` 样式：flex 居中、`height:100%`、`color:var(--text2)`、`font-size:.95rem`、`padding:40px 20px`
  - 涉及文件：`webui_static/app.js`、`webui_static/style.css`
  - 依赖任务：#272
  - 验收标准：选中空会话 → 消息区域显示"开始与智能体对话 ✨"提示；有消息时正常显示消息列表

### #276 会话列表自动刷新

- [ ] 智能体对话 Tab 活跃期间每 30 秒自动刷新会话列表
  - 新增全局变量：`let chatRefreshTimer = null`
  - 新增 `startChatRefresh()` 函数：`setInterval` 每 30 秒调用 `loadAgentChatSessions()`（仅在 `currentTab === 'agent-chat' && agentChatEnabled` 时）
  - 新增 `stopChatRefresh()` 函数：清除定时器
  - 修改 `switchTab(tab)`：当 `tab === 'agent-chat'` 时调用 `startChatRefresh()`，否则调用 `stopChatRefresh()`
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：无
  - 验收标准：Tab 活跃期间 → 会话列表每 30 秒自动刷新；切换到其他 Tab → 停止刷新；其他客户端创建的会话也能显示

### #277 新建会话对话框点击遮罩关闭

- [ ] 为新建会话对话框的遮罩层添加点击关闭事件
  - 修改 `index.html`：为 `new-session-dialog` 添加 `onclick="hideNewSessionDialog()"`
  - 修改 `index.html`：为内部 `dialog-box` 添加 `onclick="event.stopPropagation()"`
  - 涉及文件：`webui_static/index.html`
  - 依赖任务：无
  - 验收标准：点击对话框外部灰色遮罩 → 对话框关闭；点击对话框内部 → 不关闭

### #278 消息发送失败恢复

- [ ] 发送失败时保留用户输入内容到输入框，允许修改后重新发送
  - 修改 `sendAgentChatMessage()`：
    - 发送失败（`r.success === false`）：移除已添加的用户消息（`currentChatMessages.pop()`），同步更新缓存，恢复输入框内容（`input.value = content`），显示 Toast 错误提示
    - 网络异常（`catch`）：同样移除用户消息、更新缓存、恢复输入框内容、显示 Toast
    - 不再添加 `role:'system'` 的错误气泡
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#272
  - 验收标准：发送失败 → 输入框恢复用户刚才输入的内容 → 用户可修改后重新发送；对话区域不显示错误气泡

---

## 3. 样式扩展

### #279 配置页面样式扩展

- [ ] 在 `style.css` 中新增配置页面相关样式
  - `.config-nav`：flex wrap 布局、gap 6px、padding 8px 12px、background var(--card)、border 1px solid var(--border)、border-radius 8px、position sticky、top 0、z-index 10、margin-bottom 16px
  - `.config-nav-btn`：padding 4px 10px、font-size .75rem、background var(--bg)、border 1px solid var(--border)、color var(--text2)、border-radius 4px、cursor pointer、transition background .15s + color .15s
  - `.config-nav-btn:hover`：background var(--accent)、color #fff、border-color var(--accent)
  - `.config-global-error`：background rgba(225,112,85,.12)、border 1px solid var(--red)、border-radius 8px、padding 12px 16px、margin-bottom 16px、color var(--red)、font-size .85rem、white-space pre-wrap
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：配置分组导航栏样式正确（sticky 顶部、按钮 hover 变色）；全局错误提示样式醒目（红色边框、半透明红色背景）

### #280 思考动画样式

- [ ] 在 `style.css` 中新增思考动画相关样式（替换旧的 `.thinking-indicator` 简单文本样式）
  - 删除旧的 `.thinking-indicator` 样式（第 177 行：`align-self:flex-start;color:var(--text-secondary);font-size:.85rem;padding:8px 14px`）
  - 新增 `.thinking-indicator`：align-self flex-start、display flex、align-items center、gap 8px、padding 10px 14px、background var(--bg)、border 1px solid var(--border)、border-radius 12px、border-bottom-left-radius 4px、color var(--text2)、font-size .85rem
  - 新增 `.thinking-dots`：display flex、gap 4px
  - 新增 `.thinking-dot`：width 6px、height 6px、border-radius 50%、background var(--accent)、animation thinkingBounce 1.2s infinite ease-in-out
  - 新增 `.thinking-dot:nth-child(2)`：animation-delay 0.15s
  - 新增 `.thinking-dot:nth-child(3)`：animation-delay 0.3s
  - 新增 `@keyframes thinkingBounce`：0%/60%/100% → transform translateY(0) + opacity 0.4；30% → transform translateY(-6px) + opacity 1
  - 新增 `.thinking-text`：font-size .8rem
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：思考指示器显示为带动画的脉冲点 + "思考中"文本；3 个圆点依次弹跳；视觉风格与深色主题一致

### #281 空会话提示样式

- [ ] 在 `style.css` 中新增空会话提示样式
  - 新增 `.chat-empty-hint`：display flex、align-items center、justify-content center、height 100%、color var(--text2)、font-size .95rem、text-align center、padding 40px 20px
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：空会话提示居中显示、颜色为次要文本色、不遮挡消息区域

---

## 4. 验证

### #282 配置页面功能验证

- [ ] 手动验证配置页面修复后的功能
  - 验证配置页面显示所有分组（含 agent_chat、agent_optimization、delayed_trigger 等新增分组）
  - 验证布尔字段勾选状态与实际值一致，保存时正确传递
  - 验证数值字段显示正确（0 显示为 0，非 NaN）
  - 验证密码字段显示为密码输入框，placeholder 提示脱敏
  - 验证数组字段显示为逗号分隔文本
  - 验证保存成功后输入框值平滑更新（无页面闪烁）
  - 验证保存失败后错误信息显示在配置区域顶部，用户编辑内容不丢失
  - 验证分组导航栏显示和锚点跳转功能
  - 涉及文件：`webui_static/app.js`、`webui_static/index.html`、`webui_static/style.css`
  - 依赖任务：#268、#269、#270、#271、#279
  - 验收标准：所有配置页面修复项功能正常

### #283 智能体对话 Tab 功能验证

- [ ] 手动验证智能体对话 Tab 修复后的功能
  - 验证会话切换消息保持（A→B→A，A 的消息不丢失）
  - 验证会话列表显示聊天流实际名称（群聊显示 [群聊] 群名称，私聊显示 [私聊] 昵称的私聊）
  - 验证会话信息栏显示完整信息（会话 ID + 关联聊天流名称 + 消息数量）
  - 验证思考状态动画（脉冲点 + "思考中"文本，收到响应后消失）
  - 验证空会话提示（新建会话后显示"开始与智能体对话 ✨"）
  - 验证会话列表自动刷新（等待 30 秒后列表更新）
  - 验证新建会话对话框点击遮罩关闭
  - 验证消息发送失败后输入框恢复内容
  - 验证会话列表按最后活跃时间倒序排列
  - 涉及文件：`webui_static/app.js`、`webui_static/index.html`、`webui_static/style.css`
  - 依赖任务：#272、#273、#274、#275、#276、#277、#278、#280、#281
  - 验收标准：所有智能体对话 Tab 修复项功能正常