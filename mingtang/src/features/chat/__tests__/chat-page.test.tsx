/**
 * ChatPage 聊天主界面测试（R3-1-6 测试先行）
 *
 * 核心验收（REQ-R3-01 / REQ-R3-02 / REQ-R3-04）：
 * - 渲染 + tabs 状态 + 首个固定 webui-default
 * - 桌面/移动布局（ChatWorkspaceSidebar + ChatHeaderBar + MessageList + ChatComposer）
 * - 多标签打开/切换/关闭
 * - 虚拟标签 localStorage 恢复
 * - VirtualIdentityDialog 入口
 * - ws 直接消费（useChatSession + useRuntimeStatus——不重写 ws 层）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, screen } from '@testing-library/react'
import { createElement } from 'react'

import { ChatPage } from '../index'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'count' in opts) return `${key}(${opts.count})`
      return key
    },
  }),
}))

vi.mock('@/lib/avatar-url', () => ({
  useResolvedAvatarUrl: () => undefined,
}))

vi.mock('@/lib/chat-ws-client', () => ({
  chatWsClient: {
    openSession: vi.fn(async () => {}),
    onSessionMessage: vi.fn(() => () => {}),
    sendMessage: vi.fn(async () => {}),
    closeSession: vi.fn(async () => {}),
    updateNickname: vi.fn(async () => {}),
  },
}))

vi.mock('@/lib/unified-ws', () => ({
  unifiedWsClient: {
    onStatusChange: vi.fn((listener: (status: string) => void) => {
      listener('connected')
      return () => {}
    }),
    getStatus: vi.fn(() => 'connected'),
  },
}))

vi.mock('@/lib/maisaka-monitor-client', () => ({
  maisakaMonitorClient: {
    subscribe: vi.fn(async () => vi.fn(async () => {})),
  },
}))

// person-api mock——VirtualIdentityDialog 数据源
vi.mock('@/lib/person-api', () => ({
  getPlatforms: vi.fn(async () => []),
  getPersons: vi.fn(async () => []),
}))

beforeEach(() => {
  localStorage.clear()
})

describe('R3-1-6：ChatPage 聊天主界面组装', () => {
  it('渲染页面骨架 + 首个固定 webui-default 标签', () => {
    const { container } = render(createElement(ChatPage))
    // 首个固定标签 webui-default——botNameFallback（mock t 返回 key）
    expect(container.textContent).toContain('chat.botNameFallback')
  })

  it('渲染桌面侧边栏（ChatWorkspaceSidebar）', () => {
    const { container } = render(createElement(ChatPage))
    // 侧边栏标题
    expect(container.textContent).toContain('chat.sidebar.title')
  })

  it('渲染头部栏（ChatHeaderBar）', () => {
    const { container } = render(createElement(ChatPage))
    // 头部重连按钮
    expect(container.querySelector('button[aria-label="chat.actions.reconnect"]')).not.toBeNull()
  })

  it('渲染消息列表（MessageList）+ 输入框（ChatComposer）', () => {
    const { container } = render(createElement(ChatPage))
    // ChatComposer 的 textarea
    expect(container.querySelector('textarea')).not.toBeNull()
  })

  it('渲染新建虚拟会话入口', () => {
    const { container } = render(createElement(ChatPage))
    const newBtn = container.querySelector('button[aria-label="chat.sidebar.newVirtual"]')
    expect(newBtn).not.toBeNull()
  })

  it('点击新建虚拟会话打开 VirtualIdentityDialog', () => {
    const { container } = render(createElement(ChatPage))
    const newBtn = container.querySelector('button[aria-label="chat.sidebar.newVirtual"]')!
    fireEvent.click(newBtn)
    // Dialog 打开后显示标题
    expect(screen.getByText('chat.dialog.title')).toBeTruthy()
  })

  it('虚拟标签 localStorage 恢复', () => {
    // 预置一个虚拟标签
    const savedTab = {
      id: 'v-restored',
      label: '恢复的虚拟会话',
      virtualConfig: {
        platform: 'qq',
        personId: 'p1',
        userId: 'u1',
        userName: '虚拟用户',
        groupName: '',
        groupId: 'g1',
      },
      createdAt: Date.now(),
    }
    localStorage.setItem('maibot_webui_virtual_tabs', JSON.stringify([savedTab]))

    const { container } = render(createElement(ChatPage))
    // 恢复的虚拟标签显示
    expect(container.textContent).toContain('恢复的虚拟会话')
  })

  it('webui-default 标签不可关闭', () => {
    const { container } = render(createElement(ChatPage))
    // webui-default 无关闭按钮
    const closeBtns = container.querySelectorAll('button[aria-label^="chat.sidebar.closeConversation"]')
    // 初始只有 webui-default——无关闭按钮
    expect(closeBtns).toHaveLength(0)
  })
})