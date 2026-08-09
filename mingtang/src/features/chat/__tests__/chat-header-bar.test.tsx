/**
 * ChatHeaderBar 聊天头部信息栏测试（R3-1-5 测试先行——孤儿复用 ADR-6 选项 A）
 *
 * 核心验收：
 * - 头像/标题/连接状态指示点渲染
 * - 连接中/已连接/未连接三态显示
 * - 重连按钮触发 onReconnect
 * - 虚拟会话显示虚拟身份信息
 */
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { createElement } from 'react'

import { ChatHeaderBar } from '../components/chat-header-bar'
import type { ChatTab } from '../types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'name' in opts) return `${key}(${opts.name})`
      return key
    },
  }),
}))

vi.mock('@/lib/avatar-url', () => ({
  useResolvedAvatarUrl: () => undefined,
}))

function tab(overrides: Partial<ChatTab> = {}): ChatTab {
  return {
    id: 'webui-default',
    type: 'webui',
    label: 'MaiBot',
    messages: [],
    isConnected: true,
    isTyping: false,
    sessionInfo: { bot_name: 'MaiBot', bot_qq: '10001' },
    ...overrides,
  }
}

const baseProps = {
  activeTab: tab() as ChatTab | undefined,
  botDisplayName: 'MaiBot',
  isConnecting: false,
  isLoadingHistory: false,
  onReconnect: () => {},
}

describe('R3-1-5：ChatHeaderBar 孤儿复用', () => {
  it('渲染标题 + 头像', () => {
    const { container } = render(createElement(ChatHeaderBar, baseProps))
    expect(container.textContent).toContain('MaiBot')
  })

  it('已连接状态显示 connected 文案', () => {
    const { container } = render(createElement(ChatHeaderBar, baseProps))
    expect(container.textContent).toContain('chat.status.connected')
  })

  it('连接中状态显示 connecting 文案', () => {
    const props = {
      ...baseProps,
      activeTab: tab({ isConnected: false }),
      isConnecting: true,
    }
    const { container } = render(createElement(ChatHeaderBar, props))
    expect(container.textContent).toContain('chat.status.connecting')
  })

  it('未连接状态显示 disconnected 文案', () => {
    const props = {
      ...baseProps,
      activeTab: tab({ isConnected: false }),
      isConnecting: false,
    }
    const { container } = render(createElement(ChatHeaderBar, props))
    expect(container.textContent).toContain('chat.status.disconnected')
  })

  it('重连按钮触发 onReconnect', () => {
    const onReconnect = vi.fn()
    const { container } = render(createElement(ChatHeaderBar, { ...baseProps, onReconnect }))
    const reconnectBtn = container.querySelector('button[aria-label="chat.actions.reconnect"]')!
    fireEvent.click(reconnectBtn)
    expect(onReconnect).toHaveBeenCalledTimes(1)
  })

  it('连接中时重连按钮 disabled', () => {
    const props = {
      ...baseProps,
      activeTab: tab({ isConnected: false }),
      isConnecting: true,
    }
    const { container } = render(createElement(ChatHeaderBar, props))
    const reconnectBtn = container.querySelector('button[aria-label="chat.actions.reconnect"]')!
    expect(reconnectBtn.hasAttribute('disabled')).toBe(true)
  })

  it('加载历史时显示 loading 指示', () => {
    const props = { ...baseProps, isLoadingHistory: true }
    const { container } = render(createElement(ChatHeaderBar, props))
    // loading spinner（aria-hidden 的 svg）
    const spinners = container.querySelectorAll('svg.animate-spin')
    expect(spinners.length).toBeGreaterThan(0)
  })

  it('虚拟会话显示虚拟身份信息', () => {
    const props = {
      ...baseProps,
      activeTab: tab({
        type: 'virtual',
        virtualConfig: {
          platform: 'qq',
          personId: 'p1',
          userId: 'u1',
          userName: '虚拟小明',
          groupName: '测试群',
          groupId: 'g1',
        },
      }),
    }
    const { container } = render(createElement(ChatHeaderBar, props))
    expect(container.textContent).toContain('虚拟小明')
    expect(container.textContent).toContain('qq')
  })

  it('activeTab 为 undefined 时不崩溃', () => {
    const props = { ...baseProps, activeTab: undefined }
    const { container } = render(createElement(ChatHeaderBar, props))
    // 未连接态
    expect(container.textContent).toContain('chat.status.disconnected')
  })
})