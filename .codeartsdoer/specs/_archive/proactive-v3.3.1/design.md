# 1. 实现模型

## 1.1 上下文视图

v3.3.1 是 v3.3 的 WebUI 体验修复版本，聚焦于两大方向：

```
配置页面（+动态分组渲染 + 字段交互修复 + 保存校验反馈 + 分组导航）  ← 修复
智能体对话 Tab（+会话消息缓存 + 聊天流显示名称 + 思考动画 + 交互改进）  ← 修复
```

核心变化：
- 修改 `app.js`，重写 `loadConfig()` 为动态分组渲染，修复布尔/数值/密码字段交互，优化保存反馈
- 修改 `app.js`，引入会话消息本地缓存（`chatMessageCache`），修复会话切换消息丢失
- 修改 `app.js`，会话列表和会话信息栏使用 `display_name` 替代截断的 session_id
- 修改 `app.js`，新增思考状态动画指示器
- 修改 `app.js`，新增会话列表自动刷新、排序、空状态提示等交互改进
- 修改 `style.css`，新增思考动画、分组导航、配置字段错误提示等样式
- 修改 `index.html`，新增配置分组导航栏、思考动画元素
- 不修改后端 Python 代码（`webui.py`、`agent_chat.py`、`config.py`）

## 1.2 服务/组件总体架构

```
webui_static/
  ├── index.html（扩展：配置分组导航栏、思考动画元素）
  ├── style.css（扩展：思考动画、分组导航、错误提示样式）
  └── app.js（重写：配置动态渲染 + 会话消息缓存 + 显示名称 + 交互改进）
        ├── 配置页面模块
        │     ├── loadConfig() — 动态遍历 API 返回的所有分组键
        │     ├── renderConfigSection() — 单个分组的渲染函数
        │     ├── saveConfig() — 增量保存 + 字段级错误反馈
        │     └── 分组标题映射表 SECTION_TITLES
        ├── 智能体对话模块
        │     ├── chatMessageCache — Map<session_id, Message[]>
        │     ├── selectChatSession() — 缓存保存/恢复逻辑
        │     ├── renderSessionList() — 使用 display_name + 排序
        │     ├── sendAgentChatMessage() — 思考动画 + 错误恢复
        │     └── 会话列表定时刷新
        └── 通用工具
              ├── escapeHtml()
              ├── showToast()
              └── fetchJSON() / postJSON()
```

## 1.3 实现设计文档

### 1.3.1 配置页面动态分组渲染

**设计思路**：当前 `loadConfig()` 使用硬编码的 `sections` 对象（12 个分组键），遗漏了 `agent_chat`、`agent_optimization`、`delayed_trigger` 等 v3.3 新增分组。改为动态遍历配置 API 返回的所有顶层键作为分组，配合中文标题映射表。

**核心数据结构**：

```javascript
// 分组标题映射表（已知分组键 → 中文标题，未知键直接使用键名）
const SECTION_TITLES = {
  plugin: '插件',
  trigger: '触发',
  cooldown: '冷却',
  analysis: '分析',
  deepseek: 'DeepSeek',
  scope: '白名单',
  prompt: '提示词',
  webui: 'WebUI',
  smart_cleanup: '智能清理',
  status: '状态',
  delayed_trigger: '延迟触发',
  react: 'ReAct 循环',
  context_compress: '上下文压缩',
  deepseek_context: '1M 上下文',
  agent_chat: '智能体对话',
  deepseek_v4: 'DeepSeek v4',
  agent_memory: '智能体记忆',
  deepseek_optimization: 'DeepSeek 优化',
  agent_optimization: '智能体优化',
};
```

**渲染逻辑**：

```javascript
async function loadConfig() {
  const d = await fetchJSON('/api/proactive-chat/config');
  originalConfig = JSON.parse(JSON.stringify(d));

  // 动态遍历所有顶层键
  const sectionKeys = Object.keys(d);

  let html = '';
  for (const key of sectionKeys) {
    const sectionData = d[key];
    // 跳过非对象值（如顶层标量字段）
    if (typeof sectionData !== 'object' || sectionData === null) continue;

    const title = SECTION_TITLES[key] || key;
    html += renderConfigSection(key, title, sectionData);
  }

  html += '<div class="config-actions"><button onclick="saveConfig()">保存配置</button></div>';
  document.getElementById('config-content').innerHTML = html;
}
```

**单分组渲染函数**：

```javascript
function renderConfigSection(sectionKey, title, data) {
  let html = `<div class="config-section" id="config-section-${sectionKey}">`;
  html += `<h3>${title}</h3>`;

  for (const [fieldKey, fieldValue] of Object.entries(data)) {
    html += renderConfigField(sectionKey, fieldKey, fieldValue);
  }

  html += '</div>';
  return html;
}
```

**字段渲染函数**（修复布尔/数值/密码交互）：

```javascript
function renderConfigField(sectionKey, fieldKey, fieldValue) {
  const fullKey = `${sectionKey}.${fieldKey}`;
  const isPassword = fieldKey === 'deepseek_api_key';
  const isBoolean = typeof fieldValue === 'boolean';
  const isNumber = typeof fieldValue === 'number';

  let html = '<div class="config-field">';
  html += `<span class="config-label">${fieldKey}</span>`;

  if (isBoolean) {
    // 布尔字段：使用 checkbox，checked 属性与实际值严格对应
    const checked = fieldValue ? 'checked' : '';
    html += `<input type="checkbox" class="config-input" data-key="${fullKey}" ${checked}>`;
  } else if (isPassword) {
    // 密码字段：使用 password 类型，placeholder 提示脱敏
    html += `<input type="password" class="config-input" data-key="${fullKey}" value="${escapeAttr(String(fieldValue))}" placeholder="已脱敏，留空则保留原值">`;
  } else if (isNumber) {
    // 数值字段：使用 number 类型，直接显示数值
    html += `<input type="number" class="config-input" data-key="${fullKey}" value="${fieldValue}">`;
  } else if (Array.isArray(fieldValue)) {
    // 数组字段：使用文本输入，逗号分隔
    const displayVal = fieldValue.join(', ');
    html += `<input type="text" class="config-input" data-key="${fullKey}" data-type="array" value="${escapeAttr(displayVal)}">`;
  } else {
    // 文本字段
    html += `<input type="text" class="config-input" data-key="${fullKey}" value="${escapeAttr(String(fieldValue ?? ''))}">`;
  }

  html += `<span class="config-error" id="error-${fullKey.replace('.', '-')}"></span>`;
  html += '</div>';
  return html;
}
```

**关键修复点**：
1. **布尔字段**：`checked` 属性仅在 `fieldValue === true` 时添加，保存时读取 `el.checked`（布尔值），而非 `el.value`
2. **数值字段**：`value` 直接赋值为数值（`fieldValue`），不再通过 `typeof fv==='boolean'?'':fv` 的三元表达式
3. **密码字段**：使用 `type="password"` + `placeholder` 提示脱敏，保存时若值为空则不覆盖原值
4. **数组字段**：新增数组类型识别，使用逗号分隔的文本输入

### 1.3.2 配置保存校验反馈

**设计思路**：当前保存失败时仅显示 Toast 提示，然后调用 `loadConfig()` 重新渲染整个页面，导致用户编辑内容丢失。改为：保存成功时平滑更新 `originalConfig`；保存失败时在对应字段旁显示错误信息，保留用户编辑内容。

**保存逻辑**：

```javascript
async function saveConfig() {
  const updates = {};

  document.querySelectorAll('.config-input').forEach(el => {
    const [sec, field] = el.dataset.key.split('.');
    if (!updates[sec]) updates[sec] = {};

    if (el.type === 'checkbox') {
      updates[sec][field] = el.checked;
    } else if (el.type === 'number') {
      const numVal = parseFloat(el.value);
      // 数值为 NaN 时不提交该字段，保留原值
      if (!isNaN(numVal)) updates[sec][field] = numVal;
    } else if (el.dataset.type === 'array') {
      // 数组字段：按逗号分隔并去除空项
      updates[sec][field] = el.value.split(',').map(s => s.trim()).filter(s => s);
    } else if (el.type === 'password') {
      // 密码字段：空值不提交，保留原值
      if (el.value) updates[sec][field] = el.value;
    } else {
      updates[sec][field] = el.value;
    }
  });

  // 清除所有字段错误提示
  document.querySelectorAll('.config-error').forEach(el => el.textContent = '');

  if (!confirm('确认保存配置修改？')) return;

  const r = await postJSON('/api/proactive-chat/config', updates);

  if (r.success) {
    showToast('保存成功', '配置已更新');
    // 平滑更新：重新获取配置但保留页面结构
    const newConfig = await fetchJSON('/api/proactive-chat/config');
    originalConfig = JSON.parse(JSON.stringify(newConfig));
    // 仅更新输入框的值，不重建 DOM
    updateConfigValues(newConfig);
  } else {
    showToast('保存失败', r.error || '未知错误');
    // 尝试在对应字段旁显示错误
    showConfigErrors(r.error);
  }
}
```

**平滑更新函数**（不重建 DOM）：

```javascript
function updateConfigValues(config) {
  document.querySelectorAll('.config-input').forEach(el => {
    const [sec, field] = el.dataset.key.split('.');
    const val = config[sec]?.[field];
    if (val === undefined) return;

    if (el.type === 'checkbox') {
      el.checked = val === true;
    } else if (el.type === 'password') {
      el.value = val;
    } else if (el.dataset.type === 'array' && Array.isArray(val)) {
      el.value = val.join(', ');
    } else {
      el.value = val;
    }
  });
}
```

**字段级错误显示**：

```javascript
function showConfigErrors(errorMessage) {
  // 尝试从错误消息中提取字段信息
  // 后端返回格式如 "校验失败: 1 validation error for ProactiveChatConfig
  //   cooldown -> cooldown_seconds ... "
  if (!errorMessage) return;

  // 简单策略：在配置区域顶部显示完整错误信息
  const content = document.getElementById('config-content');
  const existing = content.querySelector('.config-global-error');
  if (existing) existing.remove();

  const errorDiv = document.createElement('div');
  errorDiv.className = 'config-global-error';
  errorDiv.style.cssText = 'background:rgba(225,112,85,.12);border:1px solid var(--red);border-radius:8px;padding:12px 16px;margin-bottom:16px;color:var(--red);font-size:.85rem;white-space:pre-wrap';
  errorDiv.textContent = errorMessage;
  content.insertBefore(errorDiv, content.firstChild);
}
```

### 1.3.3 配置分组导航

**设计思路**：v3.3 新增分组后配置页面变长，需要分组导航或锚点跳转。

**HTML 新增**（在 `tab-config` 内、`config-content` 前）：

```html
<div id="config-nav" class="config-nav" style="display:none">
  <!-- 动态填充分组导航按钮 -->
</div>
```

**导航渲染逻辑**（在 `loadConfig()` 末尾调用）：

```javascript
function renderConfigNav(sectionKeys) {
  const nav = document.getElementById('config-nav');
  if (sectionKeys.length <= 6) {
    nav.style.display = 'none';
    return;
  }

  nav.style.display = 'flex';
  nav.innerHTML = sectionKeys.map(key => {
    const title = SECTION_TITLES[key] || key;
    return `<button class="config-nav-btn" onclick="scrollToConfigSection('${key}')">${title}</button>`;
  }).join('');
}

function scrollToConfigSection(key) {
  const el = document.getElementById('config-section-' + key);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
```

**CSS 新增**：

```css
.config-nav {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  position: sticky;
  top: 0;
  z-index: 10;
}
.config-nav-btn {
  padding: 4px 10px;
  font-size: .75rem;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text2);
  border-radius: 4px;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.config-nav-btn:hover {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
```

### 1.3.4 会话消息本地缓存

**设计思路**：当前所有会话共用一个 `currentChatMessages` 数组，切换会话时 `currentChatMessages=[]` 导致消息丢失。改为使用 `Map<session_id, Message[]>` 为每个会话维护独立的消息缓存。

**核心数据结构**：

```javascript
// 会话消息缓存：session_id → Message[]
const chatMessageCache = new Map();

// 当前活跃会话的消息（从缓存中引用）
let currentChatMessages = [];
```

**缓存操作逻辑**：

```javascript
// 选中会话时：保存当前会话消息到缓存，再从缓存恢复目标会话消息
function selectChatSession(sid) {
  // 1. 保存当前会话消息到缓存
  if (currentChatSessionId && currentChatMessages.length > 0) {
    chatMessageCache.set(currentChatSessionId, [...currentChatMessages]);
  }

  // 2. 切换到目标会话
  currentChatSessionId = sid;
  renderSessionList();

  // 3. 从缓存恢复目标会话消息
  currentChatMessages = chatMessageCache.has(sid)
    ? [...chatMessageCache.get(sid)]
    : [];

  // 4. 显示对话区域
  document.getElementById('chat-empty').style.display = 'none';
  document.getElementById('chat-area').style.display = 'flex';
  renderChatMessages();

  // 5. 更新会话信息栏
  updateChatSessionInfo(sid);
}
```

**消息发送后更新缓存**：

```javascript
// 在 sendAgentChatMessage() 中，每次消息添加到 currentChatMessages 后同步更新缓存
// currentChatMessages.push({role:'user', content, timestamp: Date.now()});
// chatMessageCache.set(currentChatSessionId, [...currentChatMessages]);
```

**会话清除时释放缓存**：

```javascript
async function clearAgentChatSession() {
  if (!currentChatSessionId) return;
  if (!confirm('确认清除当前会话？')) return;

  const r = await postJSON('/api/proactive-chat/agent/chat/sessions/' + currentChatSessionId + '/clear', {});
  if (r.success) {
    // 释放缓存
    chatMessageCache.delete(currentChatSessionId);
    currentChatSessionId = '';
    currentChatMessages = [];
    document.getElementById('chat-empty').style.display = 'flex';
    document.getElementById('chat-area').style.display = 'none';
    await loadAgentChatSessions();
  } else {
    showToast('清除失败', r.error || '未知错误');
  }
}
```

**缓存容量控制**：

```javascript
const MAX_MESSAGES_PER_SESSION = 100;

// 在消息添加后检查容量
function trimCacheMessages(sessionId) {
  const msgs = chatMessageCache.get(sessionId);
  if (msgs && msgs.length > MAX_MESSAGES_PER_SESSION) {
    chatMessageCache.set(sessionId, msgs.slice(-MAX_MESSAGES_PER_SESSION));
  }
}
```

### 1.3.5 聊天流显示名称

**设计思路**：当前会话列表和会话信息栏显示截断的 `stream_context_id`（如 `abc12345...`），不友好。改为使用 `display_name` 字段显示聊天流实际名称。

**数据来源**：`GET /api/proactive-chat/streams` 返回的 `display_name` 和 `chat_type` 字段。

**实现方案**：在 `loadAgentChatSessions()` 获取会话列表后，额外调用 streams API 构建 `streamId → displayName` 映射表。

```javascript
// 聊天流显示名称映射：stream_id → { display_name, chat_type }
let streamDisplayMap = new Map();

async function loadStreamDisplayMap() {
  try {
    const r = await fetchJSON('/api/proactive-chat/streams');
    if (r.success && r.streams) {
      streamDisplayMap.clear();
      r.streams.forEach(s => {
        streamDisplayMap.set(s.stream_id, {
          display_name: s.display_name,
          chat_type: s.chat_type,
        });
      });
    }
  } catch (e) {
    // 获取失败不影响主流程
  }
}
```

**会话列表渲染**（使用显示名称）：

```javascript
function renderSessionList() {
  const el = document.getElementById('session-list');
  if (!agentChatSessions.length) {
    el.innerHTML = '<div style="padding:16px;color:var(--text-secondary);text-align:center;font-size:.85rem">暂无会话</div>';
    return;
  }

  // 按最后活跃时间倒序排列
  const sorted = [...agentChatSessions].sort((a, b) =>
    (b.last_active_at || 0) - (a.last_active_at || 0)
  );

  el.innerHTML = sorted.map(s => {
    const active = s.session_id === currentChatSessionId ? 'active' : '';
    const time = s.last_active_at
      ? new Date(s.last_active_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      : '';
    const cnt = s.message_count || 0;

    // 聊天流显示名称
    let streamLabel = '';
    if (s.stream_context_id) {
      const streamInfo = streamDisplayMap.get(s.stream_context_id);
      if (streamInfo) {
        const typePrefix = streamInfo.chat_type === 'group' ? '[群聊] ' : '[私聊] ';
        streamLabel = typePrefix + streamInfo.display_name;
      } else {
        streamLabel = s.stream_context_id.substring(0, 8) + '...';
      }
    }

    return `<div class="chat-session-item ${active}" onclick="selectChatSession('${s.session_id}')">
      <div class="session-name">${streamLabel || '会话 ' + s.session_id.substring(0, 8)}</div>
      <div class="session-meta">${time} · ${cnt}条消息</div>
    </div>`;
  }).join('');
}
```

**会话信息栏**（使用显示名称）：

```javascript
function updateChatSessionInfo(sid) {
  const session = agentChatSessions.find(x => x.session_id === sid);
  if (!session) return;

  const parts = [];
  parts.push('会话 ' + sid.substring(0, 8));

  if (session.stream_context_id) {
    const streamInfo = streamDisplayMap.get(session.stream_context_id);
    if (streamInfo) {
      const typePrefix = streamInfo.chat_type === 'group' ? '[群聊] ' : '[私聊] ';
      parts.push('关联: ' + typePrefix + streamInfo.display_name);
    } else {
      parts.push('关联: ' + session.stream_context_id.substring(0, 8) + '...');
    }
  }

  parts.push(session.message_count + ' 条消息');
  document.getElementById('chat-session-info').textContent = parts.join(' · ');
}
```

**加载时机**：在 `loadAgentChat()` 中，先加载 streams 映射，再加载会话列表。

```javascript
async function loadAgentChat() {
  const cfg = await fetchJSON('/api/proactive-chat/config');
  agentChatEnabled = cfg.agent_chat && cfg.agent_chat.agent_chat_enabled;

  if (!agentChatEnabled) {
    document.getElementById('agent-chat-disabled').style.display = 'block';
    document.getElementById('agent-chat-main').style.display = 'none';
    return;
  }

  document.getElementById('agent-chat-disabled').style.display = 'none';
  document.getElementById('agent-chat-main').style.display = 'flex';

  // 先加载聊天流显示名称映射
  await loadStreamDisplayMap();
  // 再加载会话列表
  await loadAgentChatSessions();
}
```

### 1.3.6 思考状态动画

**设计思路**：当前仅使用文本"思考中..."作为指示，无动画效果。改为使用 CSS 动画的脉冲点指示器。

**HTML 结构**（在 `chat-messages` 区域内动态插入）：

```html
<div class="thinking-indicator" id="thinking-indicator">
  <div class="thinking-dots">
    <span class="thinking-dot"></span>
    <span class="thinking-dot"></span>
    <span class="thinking-dot"></span>
  </div>
  <span class="thinking-text">思考中</span>
</div>
```

**CSS 动画**：

```css
.thinking-indicator {
  align-self: flex-start;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  border-bottom-left-radius: 4px;
  color: var(--text2);
  font-size: .85rem;
}
.thinking-dots {
  display: flex;
  gap: 4px;
}
.thinking-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: thinkingBounce 1.2s infinite ease-in-out;
}
.thinking-dot:nth-child(2) {
  animation-delay: 0.15s;
}
.thinking-dot:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes thinkingBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}
.thinking-text {
  font-size: .8rem;
}
```

**JS 插入/移除逻辑**（修改 `sendAgentChatMessage()`）：

```javascript
// 发送消息后显示思考动画
function showThinkingIndicator() {
  removeThinkingIndicator(); // 确保不重复
  const indicator = document.createElement('div');
  indicator.className = 'thinking-indicator';
  indicator.id = 'thinking-indicator';
  indicator.innerHTML = '<div class="thinking-dots"><span class="thinking-dot"></span><span class="thinking-dot"></span><span class="thinking-dot"></span></div><span class="thinking-text">思考中</span>';
  document.getElementById('chat-messages').appendChild(indicator);
  document.getElementById('chat-messages').scrollTop = document.getElementById('chat-messages').scrollHeight;
}

function removeThinkingIndicator() {
  const ti = document.getElementById('thinking-indicator');
  if (ti) ti.remove();
}
```

### 1.3.7 其他交互改进

#### 1.3.7.1 空会话提示

**设计思路**：新建会话后消息区域为空白，需要友好的空状态提示。

```javascript
function renderChatMessages() {
  const el = document.getElementById('chat-messages');

  if (currentChatMessages.length === 0) {
    el.innerHTML = '<div class="chat-empty-hint">开始与智能体对话 ✨</div>';
    return;
  }

  // ... 现有消息渲染逻辑 ...
}
```

**CSS**：

```css
.chat-empty-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text2);
  font-size: .95rem;
  text-align: center;
  padding: 40px 20px;
}
```

#### 1.3.7.2 会话列表自动刷新

**设计思路**：仅在初始加载和创建/清除会话时刷新列表，不自动更新。改为 Tab 活跃期间每 30 秒自动刷新。

```javascript
let chatRefreshTimer = null;

function startChatRefresh() {
  if (chatRefreshTimer) return;
  chatRefreshTimer = setInterval(async () => {
    if (currentTab === 'agent-chat' && agentChatEnabled) {
      await loadAgentChatSessions();
    }
  }, 30000);
}

function stopChatRefresh() {
  if (chatRefreshTimer) {
    clearInterval(chatRefreshTimer);
    chatRefreshTimer = null;
  }
}

// 在 switchTab() 中控制
function switchTab(tab) {
  // ... 现有逻辑 ...
  if (tab === 'agent-chat') {
    loadAgentChat();
    startChatRefresh();
  } else {
    stopChatRefresh();
  }
}
```

#### 1.3.7.3 新建会话对话框点击遮罩关闭

**设计思路**：当前 `new-session-dialog` 的遮罩层未绑定点击关闭事件。

```javascript
// 在 HTML 中为 dialog-overlay 添加 onclick
// <div id="new-session-dialog" class="dialog-overlay" style="display:none" onclick="hideNewSessionDialog()">
//   <div class="dialog-box" onclick="event.stopPropagation()">
//     ...
//   </div>
// </div>
```

此修改仅需在 `index.html` 中为 `new-session-dialog` 的 `dialog-overlay` 添加 `onclick="hideNewSessionDialog()"`，并在内部 `dialog-box` 上添加 `onclick="event.stopPropagation()"`。当前 HTML 已有 `dialog-box` 但缺少外层 overlay 的 onclick。

#### 1.3.7.4 消息发送失败恢复

**设计思路**：当前发送失败后以 system-bubble 显示错误，但用户无法重试。改为：发送失败时保留用户输入内容到输入框，允许修改后重新发送。

```javascript
async function sendAgentChatMessage() {
  if (!currentChatSessionId || isChatResponding) return;
  const input = document.getElementById('chat-input');
  const content = input.value.trim();
  if (!content) return;

  isChatResponding = true;
  input.value = '';
  document.getElementById('chat-send-btn').disabled = true;

  // 添加用户消息到缓存和当前列表
  currentChatMessages.push({ role: 'user', content, timestamp: Date.now() });
  chatMessageCache.set(currentChatSessionId, [...currentChatMessages]);
  renderChatMessages();

  showThinkingIndicator();

  try {
    const r = await postJSON('/api/proactive-chat/agent/chat/send', {
      session_id: currentChatSessionId,
      content: content,
    });

    removeThinkingIndicator();

    if (r.success) {
      currentChatMessages.push({ role: 'assistant', content: r.content, timestamp: Date.now() });
      chatMessageCache.set(currentChatSessionId, [...currentChatMessages]);
    } else {
      // 发送失败：移除已添加的用户消息，恢复输入框内容
      currentChatMessages.pop();
      chatMessageCache.set(currentChatSessionId, [...currentChatMessages]);
      input.value = content; // 恢复用户输入
      showToast('发送失败', r.error || '未知错误');
    }
  } catch (e) {
    removeThinkingIndicator();
    currentChatMessages.pop();
    chatMessageCache.set(currentChatSessionId, [...currentChatMessages]);
    input.value = content; // 恢复用户输入
    showToast('网络错误', '请稍后重试');
  } finally {
    isChatResponding = false;
    document.getElementById('chat-send-btn').disabled = false;
    renderChatMessages();
  }
}
```

#### 1.3.7.5 HTML 属性转义工具

**设计思路**：当前 `escapeHtml()` 仅处理文本内容，配置字段的 `value` 属性需要额外的属性转义。

```javascript
function escapeAttr(str) {
  return str.replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
}
```

# 2. 接口设计

## 2.1 总体设计

v3.3.1 不修改任何后端 API 端点，所有修改集中在前端 JavaScript/CSS/HTML。前端继续使用 v3.3 的 4 个 Agent Chat API 端点和 2 个配置 API 端点。

## 2.2 接口清单

| 接口 | 方法 | 路径 | 变更 |
|------|------|------|------|
| 配置读取 | GET | `/api/proactive-chat/config` | 无变更，前端消费方式改变（动态遍历） |
| 配置更新 | POST | `/api/proactive-chat/config` | 无变更，前端发送逻辑优化（增量保存+错误反馈） |
| 聊天流列表 | GET | `/api/proactive-chat/streams` | 无变更，前端新增消费（构建 display_name 映射） |
| 会话列表 | GET | `/api/proactive-chat/agent/chat/sessions` | 无变更 |
| 创建会话 | POST | `/api/proactive-chat/agent/chat/sessions` | 无变更 |
| 发送消息 | POST | `/api/proactive-chat/agent/chat/send` | 无变更 |
| 清除会话 | POST | `/api/proactive-chat/agent/chat/sessions/{id}/clear` | 无变更 |

# 4. 数据模型

## 4.1 设计目标

v3.3.1 不修改后端数据模型。前端新增以下数据结构：

1. **分组标题映射表**：静态常量，已知配置分组键到中文标题的映射
2. **会话消息缓存**：`Map<session_id, Message[]>`，前端内存中的消息缓存
3. **聊天流显示名称映射**：`Map<stream_id, {display_name, chat_type}>`，从 streams API 构建

## 4.2 模型实现

### 4.2.1 前端消息缓存模型

```typescript
// 消息结构（与后端 AgentChatMessage 对应）
interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number; // 毫秒时间戳
}

// 会话消息缓存
// chatMessageCache: Map<string, ChatMessage[]>
// 键：session_id
// 值：该会话的消息数组，最多 100 条
// 生命周期：会话存在期间有效，会话清除后释放
```

### 4.2.2 聊天流显示名称映射模型

```typescript
// 聊天流显示信息
interface StreamDisplayInfo {
  display_name: string; // 群名称 或 "xxx 的私聊"
  chat_type: 'group' | 'private';
}

// streamDisplayMap: Map<string, StreamDisplayInfo>
// 键：stream_id
// 值：从 /api/proactive-chat/streams 获取的显示信息
// 生命周期：Tab 活跃期间有效，切换 Tab 后可重新加载
```

### 4.2.3 配置分组标题映射

```typescript
// SECTION_TITLES: Record<string, string>
// 键：配置 API 返回的顶层分组键名
// 值：中文标题
// 未映射的键直接使用键名作为标题
```