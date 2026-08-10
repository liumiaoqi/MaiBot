/**
 * ChatScopeFilterPanel 测试（R4-1-2-2 测试先行）
 *
 * 从 dashboard 行为等价搬移——验证聊天范围筛选行为
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ChatScopeFilterPanel, type ChatScopeItem } from '../chat-scope-filter-panel'

function makeItems(count = 3): ChatScopeItem[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `chat-${i + 1}`,
    label: `聊天 ${i + 1}`,
    description: `描述 ${i + 1}`,
  }))
}

describe('ChatScopeFilterPanel 聊天范围筛选侧边栏', () => {
  describe('渲染聊天列表', () => {
    it('渲染全部聊天项', () => {
      const items = makeItems(3)
      render(<ChatScopeFilterPanel items={items} />)

      expect(screen.getByText('聊天 1')).toBeInTheDocument()
      expect(screen.getByText('聊天 2')).toBeInTheDocument()
      expect(screen.getByText('聊天 3')).toBeInTheDocument()
    })

    it('渲染描述文本', () => {
      const items = makeItems(1)
      render(<ChatScopeFilterPanel items={items} />)

      expect(screen.getByText('描述 1')).toBeInTheDocument()
    })

    it('列表为空时渲染 emptyContent', () => {
      render(<ChatScopeFilterPanel items={[]} emptyContent={<span>暂无聊天</span>} />)

      expect(screen.getByText('暂无聊天')).toBeInTheDocument()
    })
  })

  describe('选择指定聊天触发筛选回调', () => {
    it('点击聊天项触发 onItemSelect', () => {
      const onItemSelect = vi.fn()
      const items = makeItems(2)
      render(<ChatScopeFilterPanel items={items} onItemSelect={onItemSelect} />)

      fireEvent.click(screen.getByText('聊天 1'))
      expect(onItemSelect).toHaveBeenCalledWith('chat-1')
    })

    it('选中项高亮（data-active="true"）', () => {
      const items = makeItems(2)
      render(<ChatScopeFilterPanel items={items} selectedItemId="chat-2" />)

      const item1 = screen.getByText('聊天 1').closest('button')
      const item2 = screen.getByText('聊天 2').closest('button')
      expect(item1).toHaveAttribute('data-active', 'false')
      expect(item2).toHaveAttribute('data-active', 'true')
    })
  })

  describe('折叠/展开行为', () => {
    it('collapsed=true 时不渲染列表项', () => {
      const items = makeItems(2)
      render(<ChatScopeFilterPanel items={items} collapsed={true} onCollapsedChange={() => {}} />)

      expect(screen.queryByText('聊天 1')).not.toBeInTheDocument()
    })

    it('点击折叠按钮触发 onCollapsedChange', () => {
      const onCollapsedChange = vi.fn()
      const items = makeItems(1)
      render(
        <ChatScopeFilterPanel
          items={items}
          collapsed={false}
          onCollapsedChange={onCollapsedChange}
        />,
      )

      const collapseButton = screen.getByLabelText('折叠列表')
      fireEvent.click(collapseButton)
      expect(onCollapsedChange).toHaveBeenCalledWith(true)
    })

    it('collapsed=true 时点击展开按钮触发 onCollapsedChange(false)', () => {
      const onCollapsedChange = vi.fn()
      const items = makeItems(1)
      render(
        <ChatScopeFilterPanel
          items={items}
          collapsed={true}
          onCollapsedChange={onCollapsedChange}
        />,
      )

      const expandButton = screen.getByLabelText('展开列表')
      fireEvent.click(expandButton)
      expect(onCollapsedChange).toHaveBeenCalledWith(false)
    })
  })

  describe('模式切换', () => {
    it('渲染模式按钮并触发 onModeChange', () => {
      const onModeChange = vi.fn()
      const items = makeItems(1)
      render(
        <ChatScopeFilterPanel
          items={items}
          modes={[
            { label: '全部', value: 'all' },
            { label: '指定', value: 'specific' },
          ]}
          activeMode="all"
          onModeChange={onModeChange}
        />,
      )

      expect(screen.getByText('全部')).toBeInTheDocument()
      expect(screen.getByText('指定')).toBeInTheDocument()

      fireEvent.click(screen.getByText('指定'))
      expect(onModeChange).toHaveBeenCalledWith('specific')
    })

    it('activeMode 对应按钮高亮（data-active="true"）', () => {
      const items = makeItems(1)
      render(
        <ChatScopeFilterPanel
          items={items}
          modes={[
            { label: '全部', value: 'all' },
            { label: '指定', value: 'specific' },
          ]}
          activeMode="specific"
        />,
      )

      const allButton = screen.getByText('全部').closest('button')
      const specificButton = screen.getByText('指定').closest('button')
      expect(allButton).toHaveAttribute('data-active', 'false')
      expect(specificButton).toHaveAttribute('data-active', 'true')
    })
  })

  describe('主题零黑字（ADR-5）', () => {
    it('文字使用 text-foreground / text-muted-foreground（非硬编码黑色）', () => {
      const items = makeItems(1)
      const { container } = render(<ChatScopeFilterPanel items={items} title="聊天范围" />)

      expect(container.querySelector('.text-foreground')).toBeTruthy()
      expect(container.querySelector('.text-muted-foreground')).toBeTruthy()
    })
  })
})