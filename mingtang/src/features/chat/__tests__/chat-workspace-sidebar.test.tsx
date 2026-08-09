/**
 * ChatWorkspaceSidebar 桌面会话侧栏测试（R3-1-4 测试先行）
 *
 * 核心验收：
 * - 桌面会话列表渲染
 * - 点击会话触发 onSwitch
 * - 非默认标签关闭按钮触发 onClose
 * - 新建虚拟会话入口按钮触发 onAddVirtual（孤儿补全——ADR-6）
 * - 用户身份卡 + 内联编辑昵称
 */
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { createElement } from 'react'

import { ChatWorkspaceSidebar } from '../components/chat-workspace-sidebar'
import type { ChatTab } from '../types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'count' in opts) return `${key}(${opts.count})`
      if (opts && typeof opts === 'object' && 'label' in opts) return `${key}(${opts.label})`
      return key
    },
  }),
}))

// avatar-url mock——避免真实 fetch
vi.mock('@/lib/avatar-url', () => ({
  useResolvedAvatarUrl: () => undefined,
}))

function tab(id: string, type: 'webui' | 'virtual' = 'webui'): ChatTab {
  return {
    id,
    type,
    label: id === 'webui-default' ? 'MaiBot' : '虚拟会话',
    messages: [],
    isConnected: true,
    isTyping: false,
    sessionInfo: { bot_name: 'MaiBot', bot_qq: '10001' },
  }
}

const baseProps = {
  className: '',
  tabs: [tab('webui-default'), tab('v1', 'virtual')] as ChatTab[],
  activeTabId: 'webui-default',
  userName: '测试用户',
  onSwitch: () => {},
  onClose: () => {},
  onAddVirtual: () => {},
  onUpdateUserName: () => {},
}

describe('R3-1-4：ChatWorkspaceSidebar 桌面会话侧栏', () => {
  it('渲染标题 + 会话数副标题', () => {
    const { container } = render(createElement(ChatWorkspaceSidebar, baseProps))
    expect(container.textContent).toContain('chat.sidebar.title')
    expect(container.textContent).toContain('chat.sidebar.subtitle(2)')
  })

  it('渲染所有会话项', () => {
    const { container } = render(createElement(ChatWorkspaceSidebar, baseProps))
    expect(container.textContent).toContain('MaiBot')
    expect(container.textContent).toContain('虚拟会话')
  })

  it('点击会话项触发 onSwitch', () => {
    const onSwitch = vi.fn()
    const { container } = render(createElement(ChatWorkspaceSidebar, { ...baseProps, onSwitch }))
    const buttons = container.querySelectorAll('button')
    const switchBtn = Array.from(buttons).find((b) => b.textContent?.includes('虚拟会话'))!
    fireEvent.click(switchBtn)
    expect(onSwitch).toHaveBeenCalledWith('v1')
  })

  it('新建虚拟会话入口按钮触发 onAddVirtual（孤儿补全）', () => {
    const onAddVirtual = vi.fn()
    const { container } = render(
      createElement(ChatWorkspaceSidebar, { ...baseProps, onAddVirtual })
    )
    const newBtn = container.querySelector('button[aria-label="chat.sidebar.newVirtual"]')!
    fireEvent.click(newBtn)
    expect(onAddVirtual).toHaveBeenCalledTimes(1)
  })

  it('webui-default 不渲染关闭按钮', () => {
    const { container } = render(createElement(ChatWorkspaceSidebar, baseProps))
    const closeBtns = container.querySelectorAll('button[aria-label^="chat.sidebar.closeConversation"]')
    // 仅虚拟标签 v1 有关闭按钮
    expect(closeBtns).toHaveLength(1)
  })

  it('点击非默认标签关闭按钮触发 onClose', () => {
    const onClose = vi.fn()
    const { container } = render(createElement(ChatWorkspaceSidebar, { ...baseProps, onClose }))
    const closeBtn = container.querySelector('button[aria-label^="chat.sidebar.closeConversation"]')!
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledWith('v1', expect.anything())
  })

  it('渲染用户身份卡 + 昵称', () => {
    const { container } = render(createElement(ChatWorkspaceSidebar, baseProps))
    expect(container.textContent).toContain('chat.sidebar.profileTitle')
    expect(container.textContent).toContain('测试用户')
  })

  it('点击编辑昵称按钮进入编辑态', () => {
    const { container } = render(createElement(ChatWorkspaceSidebar, baseProps))
    const editBtn = container.querySelector('button[aria-label="chat.sidebar.editName"]')!
    fireEvent.click(editBtn)
    // 编辑态出现 input + 保存按钮
    expect(container.querySelector('input')).not.toBeNull()
    expect(container.querySelector('button[aria-label="chat.sidebar.saveName"]')).not.toBeNull()
  })

  it('编辑昵称回车提交触发 onUpdateUserName', () => {
    const onUpdateUserName = vi.fn()
    const { container } = render(
      createElement(ChatWorkspaceSidebar, { ...baseProps, onUpdateUserName })
    )
    const editBtn = container.querySelector('button[aria-label="chat.sidebar.editName"]')!
    fireEvent.click(editBtn)
    const input = container.querySelector('input')!
    fireEvent.change(input, { target: { value: '新昵称' } })
    fireEvent.keyDown(input, {
      key: 'Enter',
      nativeEvent: { isComposing: false } as unknown as Event,
    })
    expect(onUpdateUserName).toHaveBeenCalledWith('新昵称')
  })

  it('虚拟标签显示虚拟徽章', () => {
    const { container } = render(createElement(ChatWorkspaceSidebar, baseProps))
    expect(container.textContent).toContain('chat.sidebar.virtualBadge')
  })
})