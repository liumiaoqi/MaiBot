/**
 * ChatTabBar 移动端横向会话切换条测试（R3-1-4 测试先行）
 */
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { createElement } from 'react'

import { ChatTabBar } from '../components/chat-tab-bar'
import type { ChatTab } from '../types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'defaultValue' in opts) return String(opts.defaultValue)
      return key
    },
  }),
}))

function tab(id: string, type: 'webui' | 'virtual' = 'webui'): ChatTab {
  return {
    id,
    type,
    label: id === 'webui-default' ? 'MaiBot' : '虚拟',
    messages: [],
    isConnected: true,
    isTyping: false,
    sessionInfo: { bot_name: 'MaiBot' },
  }
}

const baseProps = {
  tabs: [tab('webui-default'), tab('v1', 'virtual')] as ChatTab[],
  activeTabId: 'webui-default',
  onSwitch: () => {},
  onClose: () => {},
  onAddVirtual: () => {},
}

describe('R3-1-4：ChatTabBar 移动端会话切换条', () => {
  it('渲染所有标签 + 新建虚拟会话入口', () => {
    const { container } = render(createElement(ChatTabBar, baseProps))
    // 两个标签 + 一个新建按钮（aria-label newVirtual）
    const newBtn = container.querySelector('button[aria-label="chat.sidebar.newVirtual"]')
    expect(newBtn).not.toBeNull()
    // 标签切换按钮（含 label 文本）
    expect(container.textContent).toContain('MaiBot')
    expect(container.textContent).toContain('虚拟')
  })

  it('点击标签触发 onSwitch', () => {
    const onSwitch = vi.fn()
    const { container } = render(createElement(ChatTabBar, { ...baseProps, onSwitch }))
    // 第一个标签的切换按钮（含 MaiBot 文本的 button）
    const buttons = container.querySelectorAll('button')
    const switchBtn = Array.from(buttons).find((b) => b.textContent?.includes('MaiBot'))!
    fireEvent.click(switchBtn)
    expect(onSwitch).toHaveBeenCalledWith('webui-default')
  })

  it('点击新建虚拟入口触发 onAddVirtual', () => {
    const onAddVirtual = vi.fn()
    const { container } = render(createElement(ChatTabBar, { ...baseProps, onAddVirtual }))
    const newBtn = container.querySelector('button[aria-label="chat.sidebar.newVirtual"]')!
    fireEvent.click(newBtn)
    expect(onAddVirtual).toHaveBeenCalledTimes(1)
  })

  it('webui-default 标签不渲染关闭按钮', () => {
    const { container } = render(createElement(ChatTabBar, baseProps))
    // webui-default 无关闭按钮（aria-label closeConversation 仅非 default 标签有）
    const closeBtns = container.querySelectorAll('button[aria-label^="chat.sidebar.closeConversation"]')
    // 仅虚拟标签 v1 有关闭按钮
    expect(closeBtns).toHaveLength(1)
  })

  it('点击非默认标签关闭按钮触发 onClose', () => {
    const onClose = vi.fn()
    const { container } = render(createElement(ChatTabBar, { ...baseProps, onClose }))
    const closeBtn = container.querySelector('button[aria-label^="chat.sidebar.closeConversation"]')!
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledWith('v1', expect.anything())
  })
})