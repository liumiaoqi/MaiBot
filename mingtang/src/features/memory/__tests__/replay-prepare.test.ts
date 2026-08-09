/**
 * replay-prepare 重放数据准备测试（R3-3-1 测试先行）
 */
import { describe, expect, it } from 'vitest'

import type { ReasoningReplayResponse } from '@/lib/reasoning-process-api'

import {
  createBlankReplayMessage,
  createEditableReplayMessages,
  formatEmptyReplayResponseHint,
  formatReplayTokenSummary,
  hasReplayableImageReference,
  hasUnreplayableImagePart,
  parseReplayMessageContent,
} from '../utils/replay-prepare'
import type { StructuredPromptPayload } from '../utils/format'

function makeReplayResponse(overrides: Partial<ReasoningReplayResponse> = {}): ReasoningReplayResponse {
  return {
    response: '测试回复',
    reasoning: '',
    model_name: 'test-model',
    tool_calls: null,
    prompt_tokens: 100,
    completion_tokens: 50,
    total_tokens: 150,
    prompt_cache_hit_tokens: 0,
    prompt_cache_miss_tokens: 0,
    duration_ms: 500,
    error: null,
    ...overrides,
  }
}

describe('hasReplayableImageReference', () => {
  it('image_base64 存在 → true', () => {
    expect(hasReplayableImageReference({ image_base64: 'data:image/png;base64,...' })).toBe(true)
  })

  it('image_url 为 data URI → true', () => {
    expect(hasReplayableImageReference({ image_url: 'data:image/png;base64,...' })).toBe(true)
  })

  it('image_url 对象含 data URI → true', () => {
    expect(hasReplayableImageReference({ image_url: { url: 'data:image/jpeg;base64,...' } })).toBe(true)
  })

  it('image_path 存在 → true', () => {
    expect(hasReplayableImageReference({ image_path: '/path/to/image.png' })).toBe(true)
  })

  it('image_reference 含 image_uri → true', () => {
    expect(hasReplayableImageReference({ image_reference: { image_uri: 'file:///path' } })).toBe(true)
  })

  it('无图片引用 → false', () => {
    expect(hasReplayableImageReference({ text: '纯文本' })).toBe(false)
  })
})

describe('hasUnreplayableImagePart', () => {
  it('图片部分无可重放引用 → true', () => {
    expect(hasUnreplayableImagePart({
      type: 'image',
      image_url: 'http://example.com/image.png',
    })).toBe(true)
  })

  it('图片部分有可重放引用 → false', () => {
    expect(hasUnreplayableImagePart({
      type: 'image',
      image_base64: 'data:image/png;base64,...',
    })).toBe(false)
  })

  it('数组递归检测', () => {
    expect(hasUnreplayableImagePart([
      { type: 'text', text: '文本' },
      { type: 'image', image_url: 'http://example.com/img.png' },
    ])).toBe(true)
  })

  it('嵌套对象递归检测', () => {
    expect(hasUnreplayableImagePart({
      nested: { type: 'image_url', image_url: 'http://example.com/img.png' },
    })).toBe(true)
  })

  it('无图片部分 → false', () => {
    expect(hasUnreplayableImagePart({ type: 'text', text: '纯文本' })).toBe(false)
    expect(hasUnreplayableImagePart('字符串')).toBe(false)
  })
})

describe('createEditableReplayMessages', () => {
  it('从 prompt 消息创建可编辑列表', () => {
    const payload: StructuredPromptPayload = {
      messages: [
        { role: 'user', content: '你好' },
        { role: 'assistant', content: '回复' },
      ],
    }
    const messages = createEditableReplayMessages(payload)
    expect(messages).toHaveLength(2)
    expect(messages[0].role).toBe('user')
    expect(messages[0].contentText).toBe('你好')
    expect(messages[1].role).toBe('assistant')
    expect(messages[1].contentText).toBe('回复')
  })

  it('不可重放图片回退为文本', () => {
    const payload: StructuredPromptPayload = {
      messages: [
        {
          role: 'user',
          content: [
            { type: 'text', text: '看这张图' },
            { type: 'image', image_url: 'http://example.com/img.png' },
          ],
        },
      ],
    }
    const messages = createEditableReplayMessages(payload)
    expect(messages[0].contentText).toContain('看这张图')
    expect(messages[0].contentText).toContain('[图片')
  })

  it('null prompt 返回空数组', () => {
    expect(createEditableReplayMessages(null)).toEqual([])
  })

  it('保留 tool_call_id 和 tool_calls', () => {
    const payload: StructuredPromptPayload = {
      messages: [
        { role: 'tool', content: '结果', tool_call_id: 'call-1', tool_calls: [{ id: 'call-1' }] },
      ],
    }
    const messages = createEditableReplayMessages(payload)
    expect(messages[0].tool_call_id).toBe('call-1')
    expect(messages[0].tool_calls).toEqual([{ id: 'call-1' }])
  })
})

describe('createBlankReplayMessage', () => {
  it('创建空白 user 消息', () => {
    const msg = createBlankReplayMessage()
    expect(msg.role).toBe('user')
    expect(msg.contentText).toBe('')
    expect(msg.originalContent).toBe('')
    expect(msg.id).toContain('manual-')
  })

  it('每次生成唯一 ID', () => {
    const msg1 = createBlankReplayMessage()
    const msg2 = createBlankReplayMessage()
    expect(msg1.id).not.toBe(msg2.id)
  })
})

describe('parseReplayMessageContent', () => {
  it('originalContent 为字符串时直接返回 contentText', () => {
    expect(parseReplayMessageContent('新内容', '原始字符串')).toBe('新内容')
  })

  it('originalContent 为 null 时直接返回 contentText', () => {
    expect(parseReplayMessageContent('新内容', null)).toBe('新内容')
  })

  it('contentText 为合法 JSON 时解析', () => {
    expect(parseReplayMessageContent('{"key":"value"}', { original: true })).toEqual({ key: 'value' })
  })

  it('contentText 为非法 JSON 时回退为字符串', () => {
    expect(parseReplayMessageContent('非JSON文本', { original: true })).toBe('非JSON文本')
  })

  it('空 contentText 返回空字符串', () => {
    expect(parseReplayMessageContent('  ', { original: true })).toBe('')
  })
})

describe('formatReplayTokenSummary', () => {
  it('基本 token 摘要', () => {
    const result = makeReplayResponse({ prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 })
    const summary = formatReplayTokenSummary(result)
    expect(summary).toContain('输入 100')
    expect(summary).toContain('输出 50')
    expect(summary).toContain('总计 150')
  })

  it('有缓存命中时显示', () => {
    const result = makeReplayResponse({ prompt_cache_hit_tokens: 30, prompt_cache_miss_tokens: 70 })
    expect(formatReplayTokenSummary(result)).toContain('缓存命中 30')
  })

  it('有耗时显示', () => {
    const result = makeReplayResponse({ duration_ms: 1500 })
    expect(formatReplayTokenSummary(result)).toContain('耗时')
  })
})

describe('formatEmptyReplayResponseHint', () => {
  it('有推理和工具调用', () => {
    const result = makeReplayResponse({ response: '', reasoning: '推理内容', tool_calls: [{ id: '1' }] })
    expect(formatEmptyReplayResponseHint(result)).toBe('模型未返回正文，已返回推理内容和工具调用。')
  })

  it('仅推理', () => {
    const result = makeReplayResponse({ response: '', reasoning: '推理内容' })
    expect(formatEmptyReplayResponseHint(result)).toBe('模型未返回正文，已返回推理内容。')
  })

  it('仅工具调用', () => {
    const result = makeReplayResponse({ response: '', tool_calls: [{ id: '1' }] })
    expect(formatEmptyReplayResponseHint(result)).toBe('模型未返回正文，已返回工具调用。')
  })

  it('无任何内容', () => {
    const result = makeReplayResponse({ response: '' })
    expect(formatEmptyReplayResponseHint(result)).toBe('模型未返回正文。')
  })
})