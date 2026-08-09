/**
 * MessageRenderer 12 段类型渲染测试（R3-1-2 测试先行）
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { createElement } from 'react'

import { RenderMessageContent, RenderMessageSegment } from '../components/message-renderer'
import type { ChatMessage, MessageSegment } from '../types'

// i18n mock：支持 defaultValue 回退（原版 t() 调用均带 defaultValue）
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'defaultValue' in opts) {
        return String(opts.defaultValue)
      }
      return key
    },
  }),
}))

// sonner mock（避免 jsdom 环境副作用）
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

function seg(type: MessageSegment['type'], data: unknown = ''): MessageSegment {
  return { type, data } as MessageSegment
}

describe('R3-1-2：MessageRenderer 12 段类型', () => {
  describe('RenderMessageSegment 各段类型渲染', () => {
    it('text 段渲染文本内容', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('text', '你好') }))
      expect(container.textContent).toContain('你好')
    })

    it('image 段渲染 img 元素', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('image', 'http://x/a.png') }))
      expect(container.querySelector('img')).not.toBeNull()
    })

    it('emoji 段渲染 img 元素（max-h-32）', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('emoji', 'http://x/e.png') }))
      const img = container.querySelector('img')
      expect(img).not.toBeNull()
      expect(img?.className).toContain('max-h-32')
    })

    it('voice 段渲染 audio 元素', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('voice', 'http://x/a.mp3') }))
      expect(container.querySelector('audio')).not.toBeNull()
    })

    it('video 段渲染 video 元素', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('video', 'http://x/v.mp4') }))
      expect(container.querySelector('video')).not.toBeNull()
    })

    it('face 段渲染文本（QQ 原生表情）', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('face', '178') }))
      expect(container.textContent).not.toBe('')
    })

    it('music 段渲染占位文本', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('music') }))
      expect(container.textContent).not.toBe('')
    })

    it('file 段渲染文件信息', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('file', 'doc.pdf') }))
      expect(container.textContent).not.toBe('')
    })

    it('reply 段渲染回复块（独立块）', () => {
      const replySeg: MessageSegment = {
        type: 'reply',
        data: { target_message_id: 'm1', target_message_content: '原消息', target_message_sender_nickname: '张三' },
      }
      const { container } = render(createElement(RenderMessageSegment, { segment: replySeg }))
      // 回复块含发送者名与预览文本
      expect(container.textContent).toContain('张三')
      expect(container.textContent).toContain('原消息')
    })

    it('at 段渲染 @提及', () => {
      const atSeg: MessageSegment = {
        type: 'at',
        data: { target_user_nickname: '李四' },
      }
      const { container } = render(createElement(RenderMessageSegment, { segment: atSeg }))
      expect(container.textContent).toContain('@李四')
    })

    it('forward 段渲染占位文本', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('forward') }))
      expect(container.textContent).not.toBe('')
    })

    it('unknown 段渲染未知占位', () => {
      const { container } = render(createElement(RenderMessageSegment, { segment: seg('unknown') }))
      expect(container.textContent).not.toBe('')
    })
  })

  describe('RenderMessageContent 富文本组装', () => {
    it('普通文本消息直接渲染 content', () => {
      const msg: ChatMessage = { id: 'm1', type: 'user', content: '纯文本', timestamp: 1 }
      const { container } = render(createElement(RenderMessageContent, { message: msg }))
      expect(container.textContent).toContain('纯文本')
    })

    it('富文本消息渲染 segments（reply 独立块 + inline 段）', () => {
      const msg: ChatMessage = {
        id: 'm2',
        type: 'bot',
        content: '',
        timestamp: 2,
        message_type: 'rich',
        segments: [
          { type: 'reply', data: { target_message_id: 'm0', target_message_content: '原文', target_message_sender_nickname: '王五' } },
          { type: 'text', data: '回复内容' },
        ],
      }
      const { container } = render(createElement(RenderMessageContent, { message: msg }))
      expect(container.textContent).toContain('王五')
      expect(container.textContent).toContain('回复内容')
    })

    it('空 segments 富文本不崩溃', () => {
      const msg: ChatMessage = {
        id: 'm3',
        type: 'bot',
        content: 'fallback',
        timestamp: 3,
        message_type: 'rich',
        segments: [],
      }
      const { container } = render(createElement(RenderMessageContent, { message: msg }))
      // segments 空时回退到 content
      expect(container.textContent).toContain('fallback')
    })
  })
})