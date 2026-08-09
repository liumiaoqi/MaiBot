/**
 * tag-parse <msg>标签解析/tool call归一化/会话显示名测试（R3-3-1 测试先行）
 */
import { describe, expect, it } from 'vitest'

import type { ReasoningPromptFile, ReasoningPromptSessionInfo } from '@/lib/reasoning-process-api'

import {
  buildAvatarFallbackText,
  decodeSimpleHtmlEntity,
  extractBotSelfNames,
  extractReasoningHeaderMeta,
  formatPromptPreviewText,
  formatSchemaType,
  formatSchemaValue,
  formatSessionType,
  getFirstMessageTagAttrs,
  getReasoningRecordTitle,
  getSessionDisplayName,
  getSessionSubtitle,
  getToolCallSourceClassName,
  isBotSelfStructuredMessage,
  normalizeDisplayName,
  normalizeToolCallForDisplay,
  normalizeToolDefinition,
  parseMessageTagAttributes,
  parseNaturalTextBlocks,
  toStringList,
} from '../utils/tag-parse'
import type { StructuredPromptPayload } from '../utils/format'

function makeFile(overrides: Partial<ReasoningPromptFile> = {}): ReasoningPromptFile {
  return {
    stage: 'planner',
    session_id: 'session-1',
    resolved_session_id: null,
    session_display_name: null,
    platform: 'qq',
    chat_type: 'group',
    target_id: 'target-1',
    stem: 'stem-1',
    timestamp: null,
    text_path: null,
    html_path: null,
    json_path: null,
    output_preview: null,
    action_preview: null,
    display_title: null,
    related_json_paths: [],
    model_name: null,
    duration_ms: null,
    size: 100,
    modified_at: 1700000000,
    ...overrides,
  }
}

describe('normalizeToolCallForDisplay', () => {
  it('标准 OpenAI 格式归一化', () => {
    const result = normalizeToolCallForDisplay({
      id: 'call-1',
      function: { name: 'get_weather', arguments: { city: '北京' } },
      source: 'reasoning',
    })
    expect(result.id).toBe('call-1')
    expect(result.name).toBe('get_weather')
    expect(result.arguments).toEqual({ city: '北京' })
    expect(result.source).toBe('reasoning')
    expect(result.sourceLabel).toBe('推理中调用')
  })

  it('response 源标签', () => {
    const result = normalizeToolCallForDisplay({ source: 'response', function: { name: 'tool' } })
    expect(result.sourceLabel).toBe('正文调用')
  })

  it('缺失字段回退默认值', () => {
    const result = normalizeToolCallForDisplay({})
    expect(result.id).toBe('')
    expect(result.name).toBe('unknown')
    expect(result.arguments).toEqual({})
  })

  it('非对象输入安全降级', () => {
    const result = normalizeToolCallForDisplay(null)
    expect(result.name).toBe('unknown')
  })
})

describe('getToolCallSourceClassName', () => {
  it('reasoning 源样式', () => {
    expect(getToolCallSourceClassName('reasoning')).toContain('teal')
  })

  it('response 源样式', () => {
    expect(getToolCallSourceClassName('response')).toContain('amber')
  })

  it('其他源样式', () => {
    expect(getToolCallSourceClassName('other')).toContain('muted')
  })
})

describe('formatSchemaType', () => {
  it('字符串类型', () => {
    expect(formatSchemaType({ type: 'string' })).toBe('string')
  })

  it('数组类型联合', () => {
    expect(formatSchemaType({ type: ['string', 'null'] })).toBe('string | null')
  })

  it('数组 items 类型', () => {
    expect(formatSchemaType({ items: { type: 'integer' } })).toBe('integer[]')
  })

  it('enum 类型', () => {
    expect(formatSchemaType({ enum: ['a', 'b'] })).toBe('enum')
  })

  it('无类型信息', () => {
    expect(formatSchemaType({})).toBe('unknown')
  })
})

describe('formatSchemaValue', () => {
  it('undefined → 空字符串', () => {
    expect(formatSchemaValue(undefined)).toBe('')
  })

  it('字符串原样返回', () => {
    expect(formatSchemaValue('hello')).toBe('hello')
  })

  it('对象 JSON 序列化', () => {
    expect(formatSchemaValue({ a: 1 })).toBe('{"a":1}')
  })
})

describe('toStringList', () => {
  it('数组转字符串列表', () => {
    expect(toStringList([1, 2, 3])).toEqual(['1', '2', '3'])
  })

  it('非数组返回空', () => {
    expect(toStringList('abc')).toEqual([])
    expect(toStringList(null)).toEqual([])
  })
})

describe('normalizeToolDefinition', () => {
  it('标准工具定义归一化', () => {
    const result = normalizeToolDefinition({
      type: 'function',
      function: {
        name: 'get_weather',
        description: '获取天气',
        parameters: {
          type: 'object',
          properties: {
            city: { type: 'string', description: '城市名' },
          },
          required: ['city'],
        },
      },
    })
    expect(result.name).toBe('get_weather')
    expect(result.description).toBe('获取天气')
    expect(result.parameters).toHaveLength(1)
    expect(result.parameters[0].name).toBe('city')
    expect(result.parameters[0].required).toBe(true)
  })

  it('未命名工具回退', () => {
    const result = normalizeToolDefinition({})
    expect(result.name).toBe('未命名工具')
    expect(result.parameters).toEqual([])
  })
})

describe('normalizeDisplayName', () => {
  it('trim + toLowerCase', () => {
    expect(normalizeDisplayName('  ZhangSan  ')).toBe('zhangsan')
  })
})

describe('extractBotSelfNames', () => {
  it('从 system 消息提取机器人名字', () => {
    const payload: StructuredPromptPayload = {
      messages: [
        {
          role: 'system',
          content: '你的名字是麦麦，也有人叫你小麦、麦子。你需要关注 麦麦 与用户的对话。',
        },
      ],
    }
    const names = extractBotSelfNames(payload)
    expect(names.has('麦麦')).toBe(true)
    expect(names.has('小麦')).toBe(true)
    expect(names.has('麦子')).toBe(true)
  })

  it('无 system 消息时仅含默认名', () => {
    const names = extractBotSelfNames(null)
    expect(names.has('麦麦')).toBe(true)
    expect(names.size).toBe(1)
  })
})

describe('decodeSimpleHtmlEntity', () => {
  it('解码常见 HTML 实体', () => {
    expect(decodeSimpleHtmlEntity('&quot;hello&quot; &amp; &lt;world&gt; &apos;ok&apos;')).toBe(
      '"hello" & <world> \'ok\''
    )
  })
})

describe('parseMessageTagAttributes', () => {
  it('解析属性键值对', () => {
    const attrs = parseMessageTagAttributes('user="张三" time="12:00" msg_id="abc"')
    expect(attrs.user).toBe('张三')
    expect(attrs.time).toBe('12:00')
    expect(attrs.msg_id).toBe('abc')
  })

  it('解码 HTML 实体', () => {
    const attrs = parseMessageTagAttributes('user="&lt;test&gt;"')
    expect(attrs.user).toBe('<test>')
  })

  it('无属性返回空对象', () => {
    expect(parseMessageTagAttributes('')).toEqual({})
  })
})

describe('getFirstMessageTagAttrs', () => {
  it('提取第一个 message 标签属性', () => {
    const attrs = getFirstMessageTagAttrs('前置文本<message user="张三">内容</message>')
    expect(attrs.user).toBe('张三')
  })

  it('无标签返回空对象', () => {
    expect(getFirstMessageTagAttrs('无标签文本')).toEqual({})
  })
})

describe('isBotSelfStructuredMessage', () => {
  it('user 角色且 user 属性匹配机器人名 → true', () => {
    const botSelfNames = new Set(['麦麦', '小麦'])
    expect(isBotSelfStructuredMessage(
      { role: 'user', content: '<message user="麦麦">你好</message>' },
      botSelfNames
    )).toBe(true)
  })

  it('非 user 角色 → false', () => {
    expect(isBotSelfStructuredMessage(
      { role: 'assistant', content: '<message user="麦麦">你好</message>' },
      new Set(['麦麦'])
    )).toBe(false)
  })

  it('user 属性不匹配 → false', () => {
    expect(isBotSelfStructuredMessage(
      { role: 'user', content: '<message user="张三">你好</message>' },
      new Set(['麦麦'])
    )).toBe(false)
  })
})

describe('formatSessionType', () => {
  it('group → 群聊', () => expect(formatSessionType('group')).toBe('群聊'))
  it('private → 私聊', () => expect(formatSessionType('private')).toBe('私聊'))
  it('其他 → 未知类型', () => expect(formatSessionType('other')).toBe('未知类型'))
})

describe('getSessionDisplayName', () => {
  it('display_name 优先', () => {
    const sessionInfo: ReasoningPromptSessionInfo = {
      name: 's1', platform: 'qq', chat_type: 'group', target_id: 't1',
      resolved_session_id: null, display_name: '显示名', account_id: null, matched_current_account: false,
    }
    expect(getSessionDisplayName('原始名', sessionInfo, 'fallback')).toBe('显示名')
  })

  it('fallbackName 次之', () => {
    expect(getSessionDisplayName('原始名', undefined, 'fallback')).toBe('fallback')
  })

  it('sessionName 兜底', () => {
    expect(getSessionDisplayName('原始名', undefined, null)).toBe('原始名')
  })
})

describe('getSessionSubtitle', () => {
  it('平台 + 会话类型 + 会话 ID', () => {
    const sessionInfo: ReasoningPromptSessionInfo = {
      name: 's1', platform: 'qq', chat_type: 'group', target_id: 't1',
      resolved_session_id: 'abcdef123456', display_name: '测试', account_id: null, matched_current_account: false,
    }
    const subtitle = getSessionSubtitle(sessionInfo)
    expect(subtitle).toContain('qq')
    expect(subtitle).toContain('群聊')
    expect(subtitle).toContain('会话 abcdef12')
  })

  it('无 resolved_session_id 显示未解析', () => {
    const sessionInfo: ReasoningPromptSessionInfo = {
      name: 's1', platform: 'qq', chat_type: 'group', target_id: 't1',
      resolved_session_id: null, display_name: '测试', account_id: null, matched_current_account: false,
    }
    expect(getSessionSubtitle(sessionInfo)).toContain('未解析到真实会话')
  })

  it('无 sessionInfo 返回空字符串', () => {
    expect(getSessionSubtitle(undefined)).toBe('')
  })
})

describe('extractReasoningHeaderMeta', () => {
  it('提取会话 ID 和调用 ID', () => {
    const meta = extractReasoningHeaderMeta('会话ID: abc123\n调用ID: call-456\n剩余文本')
    expect(meta.sessionId).toBe('abc123')
    expect(meta.callId).toBe('call-456')
    expect(meta.remainingText).toBe('剩余文本')
  })

  it('中文冒号也支持', () => {
    const meta = extractReasoningHeaderMeta('会话ID：xyz\n调用ID：def')
    expect(meta.sessionId).toBe('xyz')
    expect(meta.callId).toBe('def')
  })

  it('空文本返回空 meta', () => {
    const meta = extractReasoningHeaderMeta('')
    expect(meta.sessionId).toBe('')
    expect(meta.callId).toBe('')
    expect(meta.remainingText).toBe('')
  })
})

describe('getReasoningRecordTitle', () => {
  it('构造完整标题', () => {
    const file = makeFile({ stage: 'planner', session_id: 's1', display_title: '测试标题' })
    const title = getReasoningRecordTitle(file)
    expect(title).toContain('思维管道')
    expect(title).toContain('测试标题')
  })

  it('display_title 缺失时用 stem', () => {
    const file = makeFile({ stem: 'stem-xyz', display_title: null })
    const title = getReasoningRecordTitle(file)
    expect(title).toContain('stem-xyz')
  })
})

describe('formatPromptPreviewText', () => {
  it('去掉"动作："前缀', () => {
    expect(formatPromptPreviewText('动作：发送消息')).toBe('发送消息')
  })

  it('无前缀不变', () => {
    expect(formatPromptPreviewText('普通文本')).toBe('普通文本')
  })
})

describe('buildAvatarFallbackText', () => {
  it('displayName 首字母大写', () => {
    expect(buildAvatarFallbackText('张三', 'uid-1')).toBe('张')
  })

  it('displayName 空时用 userId 后两位', () => {
    expect(buildAvatarFallbackText('', 'uid-123')).toBe('23')
  })

  it('全空时返回"用"', () => {
    expect(buildAvatarFallbackText('', '')).toBe('用')
  })
})

describe('parseNaturalTextBlocks', () => {
  it('纯文本返回单个 text 块', () => {
    const blocks = parseNaturalTextBlocks('纯文本内容')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].type).toBe('text')
  })

  it('单个 message 标签', () => {
    const blocks = parseNaturalTextBlocks('<message user="张三">你好</message>')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].type).toBe('message')
  })

  it('文本 + message 标签混合', () => {
    const blocks = parseNaturalTextBlocks('前置文本<message user="张三">你好</message>后置文本')
    expect(blocks.length).toBeGreaterThanOrEqual(2)
    expect(blocks[0].type).toBe('text')
    expect(blocks[1].type).toBe('message')
  })

  it('空 message 标签被过滤', () => {
    const blocks = parseNaturalTextBlocks('<message>  </message>')
    expect(blocks).toHaveLength(0)
  })
})