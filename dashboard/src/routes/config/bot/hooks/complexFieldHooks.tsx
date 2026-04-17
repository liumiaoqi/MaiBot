import { createJsonFieldHook } from './JsonFieldHookFactory'

export const ChatTalkValueRulesHook = createJsonFieldHook({
  emptyValue: [],
  helperText: '复杂对象数组使用 JSON 编辑。每一项对应一个聊天频率规则对象。',
  placeholder: '[\n  {\n    "platform": "",\n    "item_id": "",\n    "rule_type": "group",\n    "time": "00:00-23:59",\n    "value": 1.0\n  }\n]',
})

export const ExpressionLearningListHook = createJsonFieldHook({
  emptyValue: [],
  helperText: '表达学习配置较复杂，使用 JSON 编辑更稳妥。每一项对应一个学习规则。',
  placeholder: '[\n  {\n    "platform": "",\n    "item_id": "",\n    "rule_type": "group",\n    "use_expression": true,\n    "enable_learning": true,\n    "enable_jargon_learning": true\n  }\n]',
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

export const KeywordRulesHook = createJsonFieldHook({
  emptyValue: [],
  helperText: '关键词规则为对象数组，建议直接编辑 JSON。',
  placeholder: '[\n  {\n    "keywords": ["早安"],\n    "regex": [],\n    "reaction": "早安呀"\n  }\n]',
})

export const RegexRulesHook = createJsonFieldHook({
  emptyValue: [],
  helperText: '正则规则为对象数组，建议直接编辑 JSON。',
  placeholder: '[\n  {\n    "keywords": [],\n    "regex": ["https?://[^\\\\s]+"],\n    "reaction": "检测到链接：[0]"\n  }\n]',
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
