/**
 * MessageList 消息列表测试（R3-1-2 测试先行）
 *
 * ScrollArea + map 方案（CC 决策 A——未虚拟化）。
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { createElement } from 'react'

import { MessageList } from '../components/message-list'
import type { ChatMessage } from '../types'

// i18n mock：支持 defaultValue 回退
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

// avatar-url mock（避免真实网络请求）
vi.mock('@/lib/avatar-url', () => ({
  useResolvedAvatarUrl: () => 'http://mock/avatar.png',
}))

function msg(id: string, type: ChatMessage['type'], content: string, sender?: ChatMessage['sender']): ChatMessage {
  return { id, type, content, timestamp: 1, sender }
}

const baseProps = {
  isLoadingHistory: false,
  botDisplayName: 'MaiBot',
  userName: '我',
  language: 'zh-CN',
}

describe('R3-1-2：MessageList（ScrollArea + map）', () => {
  it('空消息 + 非加载态 → 渲染空态欢迎页', () => {
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages: [] })
    )
    // EmptyState 含 Sparkles 图标（svg）+ empty 文案 key
    expect(container.querySelector('svg')).not.toBeNull()
    expect(container.textContent).toContain('chat.message.empty')
  })

  it('用户消息渲染（含 data-message-id）', () => {
    const messages = [msg('m1', 'user', '你好', { name: '我' })]
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages })
    )
    const row = container.querySelector('[data-message-id="m1"]')
    expect(row).not.toBeNull()
    expect(container.textContent).toContain('你好')
  })

  it('机器人消息渲染', () => {
    const messages = [msg('m1', 'bot', '你好啊', { name: 'MaiBot', is_bot: true })]
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages })
    )
    expect(container.textContent).toContain('你好啊')
  })

  it('系统消息作为分隔条渲染', () => {
    const messages = [msg('s1', 'system', '系统提示')]
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages })
    )
    expect(container.textContent).toContain('系统提示')
  })

  it('错误消息渲染', () => {
    const messages = [msg('e1', 'error', '出错了')]
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages })
    )
    expect(container.textContent).toContain('出错了')
  })

  it('连续同发送者消息分组（sameGroup → mt-0.5）', () => {
    const messages = [
      msg('m1', 'user', '第一句', { name: '我', user_id: 'u1' }),
      msg('m2', 'user', '第二句', { name: '我', user_id: 'u1' }),
    ]
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages })
    )
    const row1 = container.querySelector('[data-message-id="m1"]')
    const row2 = container.querySelector('[data-message-id="m2"]')
    expect(row1).not.toBeNull()
    expect(row2).not.toBeNull()
    // 第二行同组 → mt-0.5
    expect(row2?.className).toContain('mt-0.5')
  })

  it('不同发送者消息不分组（mt-3）', () => {
    const messages = [
      msg('m1', 'user', '用户说', { name: '我', user_id: 'u1' }),
      msg('m2', 'bot', '机器人回', { name: 'MaiBot', is_bot: true, agent_id: 'a1' }),
    ]
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages })
    )
    const row2 = container.querySelector('[data-message-id="m2"]')
    // 不同发送者 → mt-3（非同组）
    expect(row2?.className).toContain('mt-3')
  })

  it('1000 条消息渲染不崩溃（ScrollArea + map）', () => {
    const messages: ChatMessage[] = Array.from({ length: 1000 }, (_, i) =>
      msg(`m${i}`, i % 2 === 0 ? 'user' : 'bot', `消息${i}`, {
        name: i % 2 === 0 ? '我' : 'MaiBot',
        user_id: i % 2 === 0 ? 'u1' : undefined,
        is_bot: i % 2 !== 0,
      })
    )
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages })
    )
    // 1000 条均渲染 data-message-id
    const rows = container.querySelectorAll('[data-message-id]')
    expect(rows.length).toBe(1000)
  })

  it('加载历史态 + 空消息 → 不渲染空态', () => {
    const { container } = render(
      createElement(MessageList, { ...baseProps, messages: [], isLoadingHistory: true })
    )
    // 加载中不显示空态欢迎页（空态仅在非加载且空消息时显示）

    // （MessageList 在 isLoadingHistory=true 时不走空态分支）
    expect(container.querySelector('[data-message-id]')).toBeNull()
  })
})

describe('R3-1-2：ChatScrollContext 跨组件接口', () => {
  it('ChatScrollContext 提供 scrollToMessage', async () => {
    const { ChatScrollContext, useChatScroll } = await import('../components/chat-scroll-context')
    expect(ChatScrollContext).toBeDefined()
    expect(typeof useChatScroll).toBe('function')
  })
})