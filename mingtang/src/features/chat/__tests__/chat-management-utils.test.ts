/**
 * chat-management-utils 工具函数测试（R3-2-1 测试先行）
 */
import { describe, expect, it } from 'vitest'

import type { ChatStream } from '@/lib/chat-management-api'

import {
  chatToTarget,
  formatRuleTarget,
  formatTimestamp,
  getChatLogicalId,
  getChatTypeLabel,
  getChatTypeText,
  getTargetDisplayName,
  getTargetRuleType,
  matchesSearch,
  matchesTypeFilter,
  MUTUAL_GROUP_CHAT_RESULT_LIMIT,
  MUTUAL_GROUP_KIND_LABEL,
  normalizeMutualGroups,
  normalizeTarget,
  serializeMutualGroups,
  targetKey,
  targetLabel,
} from '../chat-management-utils'
import type { TargetItem } from '../chat-management-utils'

/** 构造测试用 ChatStream */
function makeChat(overrides: Partial<ChatStream> = {}): ChatStream {
  return {
    id: 1,
    session_id: 'session-1',
    display_name: '测试聊天',
    chat_type: 'group',
    target_id: 'target-1',
    platform: 'qq',
    account_id: null,
    scope: null,
    user_id: null,
    user_nickname: null,
    user_cardname: null,
    group_id: 'group-1',
    group_name: '测试群',
    agent_id: 'silver_wolf',
    agent_display_name: '银狼',
    agent_color: '#55AB49',
    message_count: 100,
    expression_count: 10,
    jargon_count: 5,
    created_at: 1700000000,
    last_active_at: 1700003600,
    latest_message: '你好',
    latest_message_at: 1700003600,
    ...overrides,
  }
}

describe('formatTimestamp', () => {
  it('null 返回 -', () => {
    expect(formatTimestamp(null)).toBe('-')
  })

  it('0 返回 -', () => {
    expect(formatTimestamp(0)).toBe('-')
  })

  it('有效时间戳格式化为 MM-DD HH:mm', () => {
    const result = formatTimestamp(1700000000)
    expect(result).toMatch(/\d{2}[/]\d{2} \d{2}:\d{2}/)
  })
})

describe('getChatTypeLabel / getChatTypeText', () => {
  it('群聊返回"群聊"', () => {
    expect(getChatTypeLabel(makeChat({ chat_type: 'group' }))).toBe('群聊')
    expect(getChatTypeText('group')).toBe('群聊')
  })

  it('私聊返回"私聊"', () => {
    expect(getChatTypeLabel(makeChat({ chat_type: 'private' }))).toBe('私聊')
    expect(getChatTypeText('private')).toBe('私聊')
  })
})

describe('getChatLogicalId', () => {
  it('target_id 优先', () => {
    expect(getChatLogicalId(makeChat({ target_id: 't1', group_id: 'g1', user_id: 'u1' }))).toBe('t1')
  })

  it('群聊回退 group_id', () => {
    expect(getChatLogicalId(makeChat({ target_id: '', chat_type: 'group', group_id: 'g1' }))).toBe('g1')
  })

  it('私聊回退 user_id', () => {
    expect(getChatLogicalId(makeChat({ target_id: '', chat_type: 'private', user_id: 'u1' }))).toBe('u1')
  })

  it('全空返回 -', () => {
    expect(getChatLogicalId(makeChat({ target_id: '', group_id: null, user_id: null }))).toBe('-')
  })
})

describe('getTargetRuleType', () => {
  it('rule_type=private 返回 private', () => {
    expect(getTargetRuleType({ platform: 'qq', item_id: '1', rule_type: 'private' })).toBe('private')
  })

  it('type=private 返回 private', () => {
    expect(getTargetRuleType({ platform: 'qq', item_id: '1', type: 'private' })).toBe('private')
  })

  it('其他返回 group', () => {
    expect(getTargetRuleType({ platform: 'qq', item_id: '1', rule_type: 'group' })).toBe('group')
    expect(getTargetRuleType({ platform: 'qq', item_id: '1' })).toBe('group')
  })
})

describe('normalizeTarget', () => {
  it('null 返回 null', () => {
    expect(normalizeTarget(null)).toBeNull()
  })

  it('非对象返回 null', () => {
    expect(normalizeTarget('abc')).toBeNull()
  })

  it('空 platform 返回 null', () => {
    expect(normalizeTarget({ platform: '', item_id: '1' })).toBeNull()
  })

  it('空 item_id 返回 null', () => {
    expect(normalizeTarget({ platform: 'qq', item_id: '' })).toBeNull()
  })

  it('有效对象返回 TargetItem', () => {
    expect(normalizeTarget({ platform: 'qq', item_id: '1', rule_type: 'private' })).toEqual({
      platform: 'qq',
      item_id: '1',
      rule_type: 'private',
    })
  })

  it('rule_type 非 private 规范为 group', () => {
    expect(normalizeTarget({ platform: 'qq', item_id: '1', rule_type: 'other' })).toEqual({
      platform: 'qq',
      item_id: '1',
      rule_type: 'group',
    })
  })
})

describe('normalizeMutualGroups', () => {
  it('非数组返回空数组', () => {
    expect(normalizeMutualGroups(null)).toEqual([])
    expect(normalizeMutualGroups('abc')).toEqual([])
  })

  it('空数组返回空数组', () => {
    expect(normalizeMutualGroups([])).toEqual([])
  })

  it('有效组列表提取 targets', () => {
    const result = normalizeMutualGroups([
      { targets: [{ platform: 'qq', item_id: '1', rule_type: 'group' }] },
      { expression_groups: [{ platform: 'wx', item_id: '2' }] },
    ])
    expect(result).toHaveLength(2)
    expect(result[0].targets).toHaveLength(1)
    expect(result[1].targets).toHaveLength(1)
  })

  it('非对象元素返回 { targets: [] }', () => {
    expect(normalizeMutualGroups([null])[0]).toEqual({ targets: [] })
  })
})

describe('serializeMutualGroups', () => {
  it('序列化清理为后端格式', () => {
    const groups = [
      { targets: [{ platform: 'qq', item_id: '1', rule_type: 'group' }] },
    ]
    const result = serializeMutualGroups(groups)
    expect(result).toEqual([
      { targets: [{ platform: 'qq', item_id: '1', rule_type: 'group' }] },
    ])
  })

  it('空 targets 处理', () => {
    expect(serializeMutualGroups([{ targets: [] }])).toEqual([{ targets: [] }])
    expect(serializeMutualGroups([{}])).toEqual([{ targets: [] }])
  })
})

describe('targetKey / targetLabel', () => {
  const target: TargetItem = { platform: 'qq', item_id: '1', rule_type: 'private' }

  it('targetKey 格式 platform:item_id:type', () => {
    expect(targetKey(target)).toBe('qq:1:private')
  })

  it('targetLabel 含类型文本', () => {
    expect(targetLabel(target)).toBe('qq:1:私聊')
  })
})

describe('getTargetDisplayName', () => {
  it('映射表命中返回名称', () => {
    const map = new Map([['qq:1:group', '测试群']])
    expect(getTargetDisplayName({ platform: 'qq', item_id: '1', rule_type: 'group' }, map)).toBe('测试群')
  })

  it('未命中返回"未找到聊天流"', () => {
    expect(getTargetDisplayName({ platform: 'qq', item_id: 'x', rule_type: 'group' }, new Map())).toBe('未找到聊天流')
  })
})

describe('chatToTarget', () => {
  it('ChatStream 转 TargetItem', () => {
    const chat = makeChat()
    expect(chatToTarget(chat)).toEqual({
      platform: 'qq',
      item_id: 'target-1',
      rule_type: 'group',
    })
  })
})

describe('matchesSearch', () => {
  const chat = makeChat()

  it('空查询返回 true', () => {
    expect(matchesSearch(chat, '')).toBe(true)
    expect(matchesSearch(chat, '   ')).toBe(true)
  })

  it('匹配 display_name', () => {
    expect(matchesSearch(chat, '测试')).toBe(true)
  })

  it('匹配 session_id', () => {
    expect(matchesSearch(chat, 'session-1')).toBe(true)
  })

  it('匹配 platform', () => {
    expect(matchesSearch(chat, 'qq')).toBe(true)
  })

  it('不匹配返回 false', () => {
    expect(matchesSearch(chat, '不存在的关键词xyz')).toBe(false)
  })

  it('大小写不敏感', () => {
    expect(matchesSearch(chat, 'QQ')).toBe(true)
  })
})

describe('matchesTypeFilter', () => {
  const groupChat = makeChat({ chat_type: 'group' })
  const privateChat = makeChat({ chat_type: 'private' })

  it('all 返回 true', () => {
    expect(matchesTypeFilter(groupChat, 'all')).toBe(true)
    expect(matchesTypeFilter(privateChat, 'all')).toBe(true)
  })

  it('group 匹配群聊', () => {
    expect(matchesTypeFilter(groupChat, 'group')).toBe(true)
    expect(matchesTypeFilter(privateChat, 'group')).toBe(false)
  })

  it('private 匹配私聊', () => {
    expect(matchesTypeFilter(privateChat, 'private')).toBe(true)
    expect(matchesTypeFilter(groupChat, 'private')).toBe(false)
  })
})

describe('formatRuleTarget', () => {
  it('null 返回默认行为描述', () => {
    expect(formatRuleTarget(null)).toBe('未命中显式规则，使用默认行为')
  })

  it('is_default 返回"默认规则"', () => {
    expect(formatRuleTarget({ platform: 'qq', item_id: '1', type: 'group', is_default: true })).toBe('默认规则')
  })

  it('有效规则格式化', () => {
    expect(formatRuleTarget({ platform: 'qq', item_id: '1', type: 'group' })).toBe('qq:1:群聊')
    expect(formatRuleTarget({ platform: 'wx', item_id: '2', type: 'private' })).toBe('wx:2:私聊')
  })

  it('空 platform/item_id 用 * 替代', () => {
    expect(formatRuleTarget({ platform: '', item_id: '', type: 'group' })).toBe('*:*:群聊')
  })
})

describe('常量', () => {
  it('MUTUAL_GROUP_CHAT_RESULT_LIMIT = 50', () => {
    expect(MUTUAL_GROUP_CHAT_RESULT_LIMIT).toBe(50)
  })

  it('MUTUAL_GROUP_KIND_LABEL 三类', () => {
    expect(MUTUAL_GROUP_KIND_LABEL.expression).toBe('表达')
    expect(MUTUAL_GROUP_KIND_LABEL.jargon).toBe('黑话')
    expect(MUTUAL_GROUP_KIND_LABEL.memory).toBe('记忆')
  })
})