import { createJsonFieldHook } from './JsonFieldHookFactory'
import { createListItemEditorHook } from './ListItemEditorHookFactory'

const ruleTypeLabel = (rule: unknown) => {
  if (rule === 'private') return '私聊'
  if (rule === 'group') return '群聊'
  return rule ? String(rule) : '未指定'
}

const platformLabel = (item: Record<string, unknown>) => {
  const platform = typeof item.platform === 'string' ? item.platform.trim() : ''
  const itemId = typeof item.item_id === 'string' ? item.item_id.trim() : ''
  if (!platform && !itemId) return '全局'
  if (!platform) return itemId
  if (!itemId) return platform
  return `${platform}:${itemId}`
}

const truncate = (text: string, max = 32) => {
  if (text.length <= max) return text
  return `${text.slice(0, max)}…`
}

const collectStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter((item) => item.length > 0)
}

export const ChatTalkValueRulesHook = createListItemEditorHook({
  addLabel: '添加发言频率规则',
  helperText: '可按平台/聊天流/时段分别配置发言频率，留空表示全局。',
  emptyText: '尚未配置任何规则，将使用全局默认频率。',
  itemTitle: (item) => {
    const time =
      typeof item.time === 'string' && item.time.trim()
        ? item.time.trim()
        : '全天'
    const value =
      typeof item.value === 'number' ? item.value.toFixed(2) : '—'
    return `${platformLabel(item)} · ${ruleTypeLabel(item.rule_type)} · ${time} · 频率 ${value}`
  },
})

export const ExpressionLearningListHook = createListItemEditorHook({
  addLabel: '添加表达学习规则',
  helperText: '为不同聊天流单独配置是否启用表达/jargon 学习。',
  emptyText: '尚未配置任何学习规则。',
  itemTitle: (item) => {
    const flags: string[] = []
    if (item.use_expression) flags.push('表达')
    if (item.enable_learning) flags.push('优化学习')
    if (item.enable_jargon_learning) flags.push('jargon')
    const flagText = flags.length ? flags.join(' / ') : '全部关闭'
    return `${platformLabel(item)} · ${ruleTypeLabel(item.rule_type)} · ${flagText}`
  },
})

export const KeywordRulesHook = createListItemEditorHook({
  addLabel: '添加关键词规则',
  helperText: '匹配命中后会用 reaction 内容作为额外上下文。keywords 至少填一条，或使用正则模式。',
  emptyText: '尚未添加任何关键词规则。',
  itemTitle: (item) => {
    const keywords = collectStringList(item.keywords)
    const regex = collectStringList(item.regex)
    const reaction =
      typeof item.reaction === 'string' ? item.reaction.trim() : ''
    const left = keywords.length
      ? `关键词 ${keywords.length} 条`
      : regex.length
        ? `正则 ${regex.length} 条`
        : '未配置匹配项'
    const right = reaction ? `→ ${truncate(reaction)}` : '→ 未填写反应'
    return `${left} ${right}`
  },
})

export const RegexRulesHook = createListItemEditorHook({
  addLabel: '添加正则规则',
  helperText: '正则模式按 Python 语法编写，命中时把 reaction 作为提示注入。',
  emptyText: '尚未添加任何正则规则。',
  itemTitle: (item) => {
    const regex = collectStringList(item.regex)
    const keywords = collectStringList(item.keywords)
    const reaction =
      typeof item.reaction === 'string' ? item.reaction.trim() : ''
    const left = regex.length
      ? `正则 ${regex.length} 条`
      : keywords.length
        ? `关键词 ${keywords.length} 条`
        : '未配置匹配项'
    const right = reaction ? `→ ${truncate(reaction)}` : '→ 未填写反应'
    return `${left} ${right}`
  },
})

export const ExpressionGroupsHook = createJsonFieldHook({
  emptyValue: [],
  helperText: '表达互通组使用 JSON 编辑。每一项包含一个 expression_groups 数组。',
  placeholder: '[\n  {\n    "expression_groups": [\n      {\n        "platform": "qq",\n        "item_id": "123456",\n        "rule_type": "group"\n      }\n    ]\n  }\n]',
})

export const ExperimentalChatPromptsHook = createJsonFieldHook({
  emptyValue: [],
  helperText: '实验配置中的定向 Prompt 列表使用 JSON 编辑。每一项应包含 platform、item_id、rule_type、prompt。',
  placeholder: '[\n  {\n    "platform": "qq",\n    "item_id": "123456",\n    "rule_type": "group",\n    "prompt": "这里填写额外提示词"\n  }\n]',
})

export const MCPRootItemsHook = createJsonFieldHook({
  emptyValue: [],
  helperText: 'MCP Roots 条目为对象数组，使用 JSON 编辑。',
  placeholder: '[\n  {\n    "enabled": true,\n    "uri": "file:///Users/example/project",\n    "name": "project-root"\n  }\n]',
})

export const MCPServersHook = createJsonFieldHook({
  emptyValue: [],
  helperText: 'MCP 服务器配置结构较复杂，使用 JSON 编辑。',
  placeholder: '[\n  {\n    "name": "example-server",\n    "enabled": true,\n    "transport": "stdio",\n    "command": "uvx",\n    "args": ["example-server"],\n    "env": {},\n    "url": "",\n    "headers": {},\n    "http_timeout_seconds": 30.0,\n    "read_timeout_seconds": 300.0,\n    "authorization": {\n      "mode": "none",\n      "bearer_token": ""\n    }\n  }\n]',
})
